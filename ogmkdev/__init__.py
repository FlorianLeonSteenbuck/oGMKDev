"""ogmkdev - a lightweight IDE core: EditorConfig, languages, JetBrains run configs, debuggers."""

import warnings

__version__ = "0.1.1"

# The Python sources the index reads may hold invalid escape sequences ('\d' in a plain string). Python warns when it
# parses them: that is a fact about the user's code, not an error of this program, so the warning is not shown.
warnings.filterwarnings("ignore", message="invalid escape sequence", category=SyntaxWarning)
