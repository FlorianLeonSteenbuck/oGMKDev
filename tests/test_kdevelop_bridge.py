import os
import unittest

from ogmkdev.bridges import KDEVELOP_SOURCE
from ogmkdev.bridges import kdevelop as K
from ogmkdev.debug.gdb_mi import parse_record


class KConfigTests(unittest.TestCase):
    def test_groups_escapes_and_nested_headers(self):
        text = ("# comment\n[Project]\nName=my\\sproject\nManager=KDevCMakeManager\n"
                "[Launch][Config]\nPath=a\\nb\\\\c\n")
        groups = K.parse_kconfig(text)
        self.assertEqual(groups["Project"]["Name"], "my project")
        self.assertEqual(groups["Launch][Config"]["Path"], "a\nb\\c")

    def test_load_project_from_kdevelop_repository(self):
        path = os.path.join(KDEVELOP_SOURCE, "kdevelop.kdev4")
        if not os.path.isfile(path):
            self.skipTest("kdevelop/ source tree is missing")
        project = K.load_project(path)
        self.assertEqual(project.name, "kdevelop")
        self.assertEqual(project.manager, "KDevCMakeManager")


class MiCorpusTests(unittest.TestCase):
    def test_kdevelop_mi_transcripts_parse_with_our_parser(self):
        if not os.path.isdir(KDEVELOP_SOURCE):
            self.skipTest("kdevelop/ source tree is missing")
        lines = K.mi_corpus()
        self.assertGreater(len(lines), 10, "expected MI transcripts in KDevelop's tests")
        for line in lines:
            parse_record(line)  # raises MiParseError on any line our parser cannot read


if __name__ == "__main__":
    unittest.main()
