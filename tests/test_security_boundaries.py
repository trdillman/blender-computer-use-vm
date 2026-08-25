"""Focused host/guest security-boundary regression tests."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]
HOST_DIR = ROOT_DIR / "host"
TEST_ARTIFACT_DIR = Path(r"C:\Temp")
sys.path.insert(0, str(HOST_DIR))

from vm_controller import VMController  # type: ignore


POWERSHELL = "powershell.exe" if os.name == "nt" else "powershell"
BUILD_BOOTSTRAP_MEDIA = ROOT_DIR / "scripts" / "build_bootstrap_media.ps1"
DEPLOY_GUEST_OS = ROOT_DIR / "scripts" / "deploy_guest_os.ps1"


def run_powershell(command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command, *arguments],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_powershell_script(path: Path) -> None:
    encoded_source = base64.b64encode(path.read_bytes()).decode("ascii")
    parser_command = (
        "$tokens = $null; $errors = $null; "
        f"$source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_source}')); "
        "[System.Management.Automation.Language.Parser]::ParseInput("
        "$source, [ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors) { $errors | ForEach-Object { $_.ToString() }; exit 1 }"
    )
    result = run_powershell(parser_command)
    if result.returncode:
        raise AssertionError(f"PowerShell parse failed for {path.name}: {result.stderr}{result.stdout}")


class RecordingVMController(VMController):
    def __init__(self) -> None:
        super().__init__()
        self.commands: list[str] = []

    def _run_ps(self, cmd: str, timeout: int = 15) -> dict[str, object]:
        self.commands.append(cmd)
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}


class TestSnapshotNameBoundary(unittest.TestCase):
    def test_restore_snapshot_rejects_unsafe_names_before_powershell(self) -> None:
        controller = RecordingVMController()
        invalid_names = (
            "",
            "snapshot name",
            "golden;base",
            "golden'base",
            "golden\"base",
            "golden$(Get-Date)",
            "../golden_base",
            "x" * 65,
            "golden_base\nmalicious",
        )

        for snapshot_name in invalid_names:
            with self.subTest(snapshot_name=snapshot_name):
                with self.assertRaises(ValueError):
                    controller.restore_snapshot(snapshot_name)
                self.assertEqual(controller.commands, [])

    def test_restore_snapshot_preserves_golden_base(self) -> None:
        controller = RecordingVMController()

        result = controller.restore_snapshot("golden_base")

        self.assertEqual(result["status"], "restored")
        self.assertEqual(len(controller.commands), 1)
        self.assertIn("golden_base", controller.commands[0])


class TestBootstrapSecretAcl(unittest.TestCase):
    def test_bootstrap_secret_acl_is_explicit_sid_allowlist(self) -> None:
        secret = "A" * 32
        TEST_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="blender-cu-vm-security-", dir=TEST_ARTIFACT_DIR
        ) as output_dir:
            output_path = Path(output_dir)
            result = subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(BUILD_BOOTSTRAP_MEDIA),
                    "-OutputDir",
                    str(output_path),
                    "-ISOPath",
                    str(output_path / "unattend.iso"),
                    "-DaemonSecret",
                    secret,
                ],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn(secret, result.stdout)
            self.assertNotIn(secret, result.stderr)

            secret_artifacts = {
                "host secret": output_path / "guest_daemon_secret.txt",
                "staged guest secret": output_path / "Staging" / "guest" / "daemon_secret.txt",
                "bootstrap ISO": output_path / "unattend.iso",
            }
            artifact_acls: dict[str, dict[str, object]] = {}
            for artifact_name, artifact_path in secret_artifacts.items():
                with self.subTest(artifact=artifact_name):
                    self.assertTrue(artifact_path.is_file())
                    encoded_path = base64.b64encode(str(artifact_path).encode("utf-8")).decode("ascii")
                    acl_command = (
                        f"$secretPath = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_path}')); "
                        "$acl = Get-Acl -LiteralPath $secretPath; "
                        "$actual = @($acl.Access | ForEach-Object { "
                        "$sid = $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value; "
                        "[PSCustomObject]@{ Sid = $sid; Type = $_.AccessControlType.ToString(); "
                        "Rights = [int]$_.FileSystemRights } }) | Sort-Object Sid; "
                        "[PSCustomObject]@{ Protected = $acl.AreAccessRulesProtected; Rules = $actual } "
                        "| ConvertTo-Json -Compress"
                    )
                    acl_result = run_powershell(acl_command)
                    self.assertEqual(acl_result.returncode, 0, acl_result.stdout + acl_result.stderr)
                    artifact_acls[artifact_name] = json.loads(acl_result.stdout)

        expected_sids = {
            "S-1-5-18",
            "S-1-5-32-544",
            run_powershell("[Security.Principal.WindowsIdentity]::GetCurrent().User.Value").stdout.strip(),
        }
        for artifact_name, acl in artifact_acls.items():
            with self.subTest(artifact=artifact_name):
                rules = acl["Rules"]
                self.assertTrue(acl["Protected"])
                self.assertEqual({rule["Sid"] for rule in rules}, expected_sids)
                self.assertTrue(all(rule["Type"] == "Allow" for rule in rules))
                self.assertTrue(all(rule["Rights"] == 2032127 for rule in rules))


class TestPowerShellSecurityInvariants(unittest.TestCase):
    def test_security_scripts_parse(self) -> None:
        parse_powershell_script(BUILD_BOOTSTRAP_MEDIA)
        parse_powershell_script(DEPLOY_GUEST_OS)

    def test_bootstrap_acl_uses_sids_without_icacls(self) -> None:
        source = BUILD_BOOTSTRAP_MEDIA.read_text(encoding="utf-8")

        self.assertIn("S-1-5-18", source)
        self.assertIn("S-1-5-32-544", source)
        self.assertIn("SecurityIdentifier", source)
        self.assertIn("SetAccessRuleProtection($true, $false)", source)
        self.assertNotIn("icacls", source.lower())

    def test_host_secret_is_created_with_its_protected_acl(self) -> None:
        source = BUILD_BOOTSTRAP_MEDIA.read_text(encoding="utf-8")

        protected_acl = source.index("$SecretAcl.SetAccessRuleProtection($true, $false)")
        protected_stream = source.find("[System.IO.FileStream]::new(")
        secret_write = source.find("$SecretStream.Write(")

        self.assertGreaterEqual(protected_stream, 0)
        self.assertGreaterEqual(secret_write, 0)
        constructor = source[protected_stream:secret_write]
        self.assertLess(protected_acl, protected_stream)
        self.assertLess(protected_stream, secret_write)
        self.assertIn("$SecretAcl", constructor)
        self.assertNotIn("Set-Content -Path $HostSecretPath", source)
        self.assertNotIn('Set-Content -Path (Join-Path $GuestDest "daemon_secret.txt")', source)

    def test_deployment_never_prints_the_daemon_secret_value(self) -> None:
        source = DEPLOY_GUEST_OS.read_text(encoding="utf-8")

        self.assertNotRegex(
            source,
            r"(?im)^\s*(?:Write-Host|Write-Output|echo)\b[^\r\n]*(?:\$DaemonSecret|\$\{DaemonSecret\}|\$\([^\r\n]*DaemonSecret[^\r\n]*\))",
        )
        self.assertIn("Daemon secret file (ACL-restricted)", source)
        self.assertIn('$EscapedSecretPath = $SecretPath.Replace("\'", "\'\'")', source)
        self.assertIn("`$env:GUEST_DAEMON_SECRET = (Get-Content -LiteralPath '$EscapedSecretPath' -Raw).Trim()", source)
        self.assertNotIn('Read at runtime: Get-Content -LiteralPath', source)
        self.assertEqual(source.count("Write-DaemonSecretAccessInstructions"), 3)


if __name__ == "__main__":
    unittest.main()
