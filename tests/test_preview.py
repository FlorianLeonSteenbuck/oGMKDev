import unittest

from ogmkdev import preview as P

MARKDOWN = """# Title
Some *italic* and **bold** text with `code` and [a link](http://x.y).

- one
- two with _under_ words
  continued line

1. first
2. second

> quoted **text**

    indented code

```php
echo 1;
```

![logo](img/logo.png)
"""


def plain(spans):
    return "".join(span.text for span in spans)


class MarkdownBlocksTest(unittest.TestCase):
    def setUp(self):
        self.blocks = P.blocks_of("markdown", MARKDOWN)

    def test_the_blocks_come_in_document_order(self):
        self.assertEqual([block.kind for block in self.blocks],
                         ["heading", "paragraph", "bullet", "bullet", "ordered", "ordered",
                          "paragraph", "code", "code", "image"])

    def test_a_heading_has_its_level_and_its_text(self):
        self.assertEqual((self.blocks[0].level, plain(self.blocks[0].spans)), (1, "Title"))

    def test_emphasis_code_and_links_are_styled_spans(self):
        spans = [(span.text, span.bold, span.italic, span.code, span.target) for span in self.blocks[1].spans]
        self.assertEqual(spans, [
            ("Some ", False, False, False, ""),
            ("italic", False, True, False, ""),
            (" and ", False, False, False, ""),
            ("bold", True, False, False, ""),
            (" text with ", False, False, False, ""),
            ("code", False, False, True, ""),
            (" and ", False, False, False, ""),
            ("a link", False, False, False, "http://x.y"),
            (".", False, False, False, ""),
        ])

    def test_a_list_item_continues_on_the_next_line_and_keeps_its_emphasis(self):
        self.assertEqual(plain(self.blocks[2].spans), "one")
        self.assertEqual(plain(self.blocks[3].spans), "two with under words continued line")
        self.assertTrue(any(span.italic and span.text == "under" for span in self.blocks[3].spans))

    def test_ordered_items_keep_their_numbers(self):
        self.assertEqual([self.blocks[4].number, self.blocks[5].number], [1, 2])

    def test_a_quote_is_marked_with_its_depth(self):
        self.assertEqual(self.blocks[6].quote, 1)
        self.assertEqual(plain(self.blocks[6].spans), "quoted text")
        self.assertTrue(self.blocks[6].spans[1].bold)

    def test_indented_and_fenced_code_keep_their_text_and_language(self):
        self.assertEqual((self.blocks[7].language, self.blocks[7].text), ("", "indented code"))
        self.assertEqual((self.blocks[8].language, self.blocks[8].text), ("php", "echo 1;"))

    def test_an_image_on_a_line_of_its_own_is_an_image_block(self):
        self.assertEqual((self.blocks[9].kind, self.blocks[9].text, self.blocks[9].target),
                         ("image", "logo", "img/logo.png"))


class MarkdownOtherCasesTest(unittest.TestCase):
    def test_setext_headings_and_rules(self):
        blocks = P.blocks_of("markdown", "Sub title\n---\n\n***\n\nTop\n===\n")
        self.assertEqual([(block.kind, block.level) for block in blocks],
                         [("heading", 2), ("rule", 0), ("heading", 1)])
        self.assertEqual(plain(blocks[0].spans), "Sub title")

    def test_escapes_and_words_with_underscores_are_plain_text(self):
        blocks = P.blocks_of("markdown", "Keep \\*these\\* and snake_case_name here.\n")
        self.assertEqual(plain(blocks[0].spans), "Keep *these* and snake_case_name here.")
        self.assertFalse(any(span.italic for span in blocks[0].spans))

    def test_a_link_keeps_its_target_and_an_image_in_a_line_is_a_span(self):
        blocks = P.blocks_of("markdown", "See [docs](docs/Order.md) and ![alt text](a.png).\n")
        spans = blocks[0].spans
        self.assertEqual(spans[1].target, "docs/Order.md")
        self.assertTrue(any(span.image and span.target == "a.png" for span in spans))

    def test_a_code_fence_that_is_never_closed_reads_to_the_end(self):
        blocks = P.blocks_of("markdown", "```python\nx = 1\ny = 2\n")
        self.assertEqual([(block.kind, block.language, block.text) for block in blocks],
                         [("code", "python", "x = 1\ny = 2")])

    def test_a_list_item_without_text_is_still_an_item(self):
        blocks = P.blocks_of("markdown", "-\n- next\n")
        self.assertEqual([block.kind for block in blocks], ["bullet", "bullet"])


class BareDownBlocksTest(unittest.TestCase):
    def test_headings_paragraphs_items_quotes_code_and_rules(self):
        text = "= Title\nText with **bold** and |code|.\n- item\n~~~ python\nx = 1\n~~~\n%% a comment\n> quoted\n----\n"
        blocks = P.blocks_of("baredown", text)
        self.assertEqual([block.kind for block in blocks],
                         ["heading", "paragraph", "bullet", "code", "paragraph", "rule"])
        self.assertEqual((blocks[0].level, plain(blocks[0].spans)), (1, "Title"))
        self.assertTrue(blocks[1].spans[1].bold)
        self.assertTrue(blocks[1].spans[3].code)
        self.assertEqual((blocks[3].language, blocks[3].text), ("python", "x = 1"))
        self.assertEqual(blocks[4].quote, 1)


class KindTest(unittest.TestCase):
    def test_each_file_gets_its_kind_of_preview(self):
        self.assertEqual(P.kind_of("a/README.md"), "markdown")
        self.assertEqual(P.kind_of("notes.MARKDOWN"), "markdown")
        self.assertEqual(P.kind_of("guide.bd"), "baredown")
        self.assertEqual(P.kind_of("logo.PNG"), "image")
        self.assertEqual(P.kind_of("photo.jpeg"), "image")
        self.assertIsNone(P.kind_of("icon.svg"))  # an SVG is text: the editor shows it, the preview does not
        self.assertIsNone(P.kind_of("notes.txt"))
        self.assertEqual(P.blocks_of("image", "x"), [])


if __name__ == "__main__":
    unittest.main()
