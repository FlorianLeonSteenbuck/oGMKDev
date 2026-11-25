"""Doc comments generated from signatures: PHPDoc, JSDoc and Python docstrings."""

from ogmkdev import docblocks


def test_php_method_lists_params_and_return():
    php = ("class Cart {\n"
           "    public function total(?float $discount = null, array &$log = []): float\n"
           "    {\n    }\n}\n")
    block = docblocks.generate(php, 2, "php")
    assert block.line == 2
    assert block.text.splitlines() == ["    /**", "     *", "     * @param ?float $discount",
                                       "     * @param array $log", "     * @return float", "     */"]


def test_php_class_lists_properties_and_promoted_constructor_parameters():
    php = ("<?php\nclass Cart {\n    public string $owner;\n    private array $items = [];\n"
           "    public function __construct(private int $limit = 10) {}\n}\n")
    block = docblocks.generate(php, 2, "php")
    assert block.line == 2
    text = block.text
    assert "@property string $owner" in text and "@property array $items" in text
    assert "@property int $limit" in text


def test_php_variadic_and_untyped_params():
    php = "function join(string $glue, ...$parts)\n{\n}\n"
    text = docblocks.generate(php, 1, "php").text
    assert "@param string $glue" in text and "@param mixed ...$parts" in text
    assert "@return" not in text


def test_typescript_method_with_generics_and_return_type():
    ts = "export class Cart {\n  total<T>(items: T[], discount?: number): number {\n    return 0;\n  }\n}\n"
    block = docblocks.generate(ts, 2, "js")
    assert block.line == 2
    assert "@param {T[]} items" in block.text and "@param {number} discount" in block.text
    assert "@returns {number}" in block.text


def test_typescript_arrow_function_with_default_and_untyped_parameter():
    ts = "const add = async (a: number, b = 2): Promise<number> => a + b;\n"
    text = docblocks.generate(ts, 1, "js").text
    assert "@param {number} a" in text and "@param {*} b" in text
    assert "@returns {Promise<number>}" in text


def test_typescript_class_properties_and_constructor_parameter_properties():
    ts = ("export class Cart {\n  owner?: string;\n"
          "  constructor(private readonly limit: number = 10) {}\n}\n")
    text = docblocks.generate(ts, 3, "js").text
    assert "@property {string} owner" in text and "@property {number} limit" in text


def test_python_function_docstring_goes_below_the_header():
    py = "def total(items: list[float], discount: float = 0.0, *extra) -> float:\n    return 0.0\n"
    block = docblocks.generate(py, 1, "py")
    assert block.line == 2  # the line below the header
    assert "    Args:" in block.text and "        items (list[float]):" in block.text
    assert "        *extra (Any):" in block.text and "    Returns:" in block.text
    assert block.text.lstrip().startswith('"""') and block.text.rstrip().endswith('"""')


def test_python_class_attributes_from_annotated_body():
    py = "class Cart:\n    owner: str\n    items: list\n\n    def f(self):\n        pass\n"
    text = docblocks.generate(py, 1, "py").text
    assert "Attributes:" in text and "owner (str)" in text and "items (list)" in text


def test_no_declaration_gives_none():
    assert docblocks.generate("x = 1\n", 1, "py") is None
    assert docblocks.generate("foo(bar);\n", 1, "js") is None


def test_families_of_the_languages():
    assert docblocks.family_of("php") == "php"
    assert docblocks.family_of("tsx") == "js" and docblocks.family_of("pypy") == "py"
    assert docblocks.family_of("css") is None
