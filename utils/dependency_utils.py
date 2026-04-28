import sys
import subprocess
from pathlib import Path
from utils.logging_utils import LogManager,LogLevels


class DependencyManager:
    """Manage Python dependencies and package updates."""
    
    @classmethod
    def update_py_dependencies(cls, requirements_file: str = None, verbose: bool = False) -> bool:
        """
        Update Python dependencies from requirements.txt using pip.
        
        Args:
            requirements_file: Path to requirements.txt file. If None, looks for it in parent directory.
            verbose: If True, print pip output to console.
            
        Returns:
            bool: True if update succeeded, False otherwise.
        """
        try:
            # Determine requirements file path
            if requirements_file is None:
                # Look for requirements.txt in workspace root
                workspace_root = Path(__file__).parent.parent
                requirements_file = workspace_root / "requirements.txt"
            else:
                requirements_file = Path(requirements_file)
            
            if not requirements_file.exists():
                LogManager.log_core(
                    f"DependencyManager: Requirements file not found: {requirements_file}"
                )
                return False
            
            LogManager.log_core(
                f"DependencyManager: Updating Python dependencies from: {requirements_file}"
            )
            
            # Run pip install with requirements file
            pip_command = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "-r",
                str(requirements_file)
            ]
            
            result = subprocess.run(
                pip_command,
                capture_output=not verbose,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                LogManager.log_core(
                    "DependencyManager: Python dependencies updated successfully"
                )
                if verbose and result.stdout:
                    LogManager.log_core(result.stdout)
                return True
            else:
                error_msg = result.stderr or "Unknown pip error"
                LogManager.log_core(
                    f"DependencyManager: Pip update failed with code {result.returncode}: {error_msg}"
                )
                if verbose:
                    LogManager.log_core(f"Error: {error_msg}")
                return False
                
        except subprocess.TimeoutExpired:
            LogManager.log_core(
                "DependencyManager: Pip update timed out after 300 seconds"
            )
            return False
        except Exception as e:
            LogManager.log_core(
                f"DependencyManager: Failed to update dependencies: {str(e)}"
            )
            return False
