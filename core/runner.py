"""
DistroForge - Command Runner
Exectute shell commands with logging, dry-run support, retries, and error handling
"""

import subprocess
import time
from dataclasses import dataclass
from typing import Optional
from core.logger import ForgeLogger

@dataclass
class CommandResult:
    """Result of a command exectution"""
    command: str
    returncode: int
    stdout: str
    stderr: str
    success: bool
    skipped: bool = False
    duration: float = 0.0
    

class Runner:
    """
    Command execution engine.
    
    Handles sudo escalation, dry-run mode, logging, retries, 
    and graceful error handling for all shell commands.
    """
    
    def __init__(self, logger: ForgeLogger, dry_run: bool = False, verbose: bool = False):
        self.logger = logger
        self.dry_run = dry_run
        self.verbose = verbose
        self._sudo_cached = False
        
    def _cache_sudo(self) -> bool:
        """Pre-cache sudo credentials so commands don't prompt mid-phase."""
        if self._sudo_cached:
            return True
        try:
            result = subprocess.run(
                ["sudo", "-v"],
                timeout=60,
                capture_output=False,
            )
            if result.returncode == 0:
                self._sudo_cached = True
                return True
        except Exception:
            pass
        return False
    
    def run(self, command: str, description: str = "", sudo: bool = False, check: bool = False, retries: int = 0, retry_delay: float = 3.0, env: Optional[dict] = None, timeout: int = 60) -> CommandResult:
        """
        Execute a shell command.
        
        Args: 
            command: The shell command to run.
            description: Human-readable description for logging.
            sudo: Whether to prepend sudo.
            check: Whether to raise on failure.
            retries: Number of retry attempts on failure.
            retry_delay: Seconds to wait between retries.
            env: Optional environment variables to merge.
            timeout: Max seconds before killing the command.
            
        Returns:
            CommandResult with exectution details.
        """
        if sudo and not command.startswith("sudo "):
            command = f"sudo {command}"
        
        desc = description or command[:80]
        
        if self.dry_run:
            self.logger.dry_run(desc, command)
            return CommandResult (
                command=command,
                returncode=0,
                stdout="",
                stderr="",
                success=True,
                skipped=True
            )
        
        self.logger.command(desc)
        
        attempts = retries + 1
        last_result = None
        
        for attempt in range(1, attempts + 1):
            start = time.time()
            try:
                proc_env = None
                if env:
                    import os
                    proc_env = {**os.environ, **env}
                    
                proc = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=proc_env
                )
                
                duration = time.time() - start
                
                last_result = CommandResult(
                    command=command,
                    returncode=proc.returncode,
                    stdout=proc.stdout.strip(),
                    stderr=proc.stderr.strip(),
                    success=proc.returncode == 0,
                    duration=duration
                )
                
                if last_result.success:
                    self.logger.success(desc, duration)
                    if self.verbose and proc.stdout.strip():
                        self.logger.verbose_output(proc.stdout.strip())
                    return last_result
                
                if attempt < attempts:
                    self.logger.retry(desc, attempt, attempts, proc.stderr[:200])
                    time.sleep(retry_delay)
                else:
                    self.logger.error(desc, proc.stderr[:500])
                    if self.verbose:
                        if proc.stdout.strip():
                            self.logger.verbose_output(proc.stdout.strip())
                        self.logger.verbose_output(f"Exit code: {proc.returncode}")
                        
            except subprocess.TimeoutExpired:
                duration = time.time() - start
                last_result = CommandResult(
                    command=command,
                    returncode=-1,
                    stdout="",
                    stderr=f"Command timed out after {timeout}s",
                    success=False,
                    duration=duration
                )
                self.logger.error(desc, f"Timed out after {timeout}s")
                
            except Exception as e:
                duration = time.time() - start
                last_result = CommandResult(
                    command=command,
                    returncode=-1,
                    stdout="",
                    stderr=str(e),
                    success=False,
                    duration=duration
                )
                self.logger.error(desc, str(e))
            
        return last_result
    
    def run_batch(self, commands: list[tuple[str, str]], sudo: bool = False, stop_on_error: bool = True) -> list[CommandResult]:
        """
        Run a batch of (commann, description) tuples.
        
        Args:
            commands: List of (command_string, description) tuples.
            sudo: Apply sudo to all commands.
            stop_on_error: Stop batch if any command fails.
            
        Returns:
            List of CommandResults.
        """
        results = []
        for cmd, desc in commands:
            result = self.run(cmd, description=desc, sudo=sudo)
            results.append(result)
            if not result.success and stop_on_error and not result.skipped:
                self.logger.warning(f"Batch stopped: '{desc}' failed")
                break
        return results
    
    def check_installed(self, program: str) -> bool:
        """Check if a program is available on PATH."""
        result = self.run(f"which {program}", description=f"Checking for {program}", check=False)
        return result.success
    
    def get_version(self, program: str, flag: str = "--version") -> str:
        """
        Get the version string of an installed program.
        Returns the first line of output, or empty string if not installed.
        """
        result = self.run(f"{program} {flag} 2>/dev/null | head -1", description=f"Getting {program} version.", check=False)
        if result.success and result.stdout:
            return result.stdout.split("\n")[0].strip()
        return ""
    
    def get_output(self, command: str, default: str = "") -> str:
        """Run a command and return its stdout, or default on failure."""
        result = self.run(command, check=False)
        return result.stdout if result.success else default