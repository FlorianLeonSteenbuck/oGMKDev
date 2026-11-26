"""Ctrl+click on a path that a PHP file builds from __DIR__ opens the file next to it, in a PHP file with HTML around it.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import unittest

from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase, pump_until, write

PAGE = ('<!DOCTYPE html>\n<html>\n<head>\n<title><?php echo "Kil.ls Debts"; ?></title>\n<style type="text/css">\n'
        '<?php echo file_get_contents(__DIR__ . "/style.css"); ?>\n</style>\n</head>\n<body></body>\n</html>\n')
LINE = '<?php echo file_get_contents(__DIR__ . "/style.css"); ?>'


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class PhpPathClickTests(FrameTestCase):
    def test_ctrl_click_on_a_dir_path_opens_the_file_next_to_the_php_file(self):
        page = write(self.folder, "index.php", PAGE)
        css = write(self.folder, "style.css", "body { background: #fff; }\n")
        frame = self.frame()
        frame.open_file(page)
        self.wait_for_file(frame, page)
        frame._follow_click("style", LINE.index('"/style.css"') + 3, LINE)
        self.assertTrue(pump_until(lambda: frame.area.current_path() == css, timeout=10),
                        f"the click did not open {os.path.basename(css)}")


if __name__ == "__main__":
    unittest.main()
