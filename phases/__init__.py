"""
DistroForage - Base Phase
Abstract base class for all setup phases.
"""

from abc import ABC, abstractmethod
from core.runner import Runner
from core.logger import ForgeLogger
from core.detector import SystemInfo


class Phase(ABC):
    """
    Base class for setup phases.
    
    Each phase represents a logical group of setup steps
    (e.g., system updates, shell setup, dev tools, gaming).
    """
    
    # Subclass must define these
    name: str = "base"
    description: str = "Base phase"
    icon: str = "⚙"
    
    def __init__(self, runner: Runner, logger: ForgeLogger, config: dict, system: SystemInfo):
        self.runner = runner
        self.logger = logger
        self.config = config
        self.system = system
        self._results = {"passed": 0, "failed": 0, "skipped": 0}
        self._step_number = 0
        self._total_step = 0
        self._failed_steps: list[tuple[str, str]] = [] # (description, error)
        
    @abstractmethod
    def execute(self):
        """Run the phase. Subclasses must implement this."""
        pass
    
    def should_skip(self) -> bool:
        """
        Override to add skip logic. 
        Returns True to skip this phase entierly.
        """
        return False
    
    def run(self) -> dict:
        """Entry point to run the phase with logging. Returns results dict."""
        if self.should_skip():
            self.logger.skip(f"{self.icon} {self.name}: {self.description}")
            return self._results
        
        try:
            self.execute()
        except KeyboardInterrupt:
            self.logger.warning("Phase interrupted by user")
            raise
        except Exception as e:
            self.logger.error(f"Phase '{self.name}' failed", str(e))
            self._results["failed"] += 1

        # Print phase summary
        if self._results["failed"] > 0:
            self.logger.warning(
                f"Phase completed with {self._results['failed']} failed step(s)"
            )
            for desc, err in self._failed_steps[:5]:
                self.logger.info(f"  Failed: {desc} — {err[:100]}")
        else:
            self.logger.info(
                f"Phase complete: {self._results['passed']} passed, "
                f"{self._results['skipped']} skipped"
            )

        return self._results
    
    def step(self, message: str):
        """Log a numbered step within this phase."""
        self._step_number += 1
        self.logger.step(f"[{self._step_number}] {message}") 
        
    def cmd(self, command: str, description: str = "", **kwargs) -> bool:
        """Run a command and return success status."""
        result = self.runner.run(command, description=description, **kwargs)
        if result.success:
            self._results["passed"] += 1
        elif result.skipped:
            self._results["skipped"] += 1
        else:
            self._results["failed"] += 1
            self._failed_steps.append((description or command[:60], result.stderr[:200]))
        return result.success
    
    def installed(self, program: str) -> bool:
        """Check if a program is installed."""
        return self.runner.check_installed(program)
    
    def cfg(self, *keys, default=None):
        """Safely traverse nested config keys. e.g., cfg('dev', 'docker')."""
        val = self.config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k, default)
            else:
                return default
        return val