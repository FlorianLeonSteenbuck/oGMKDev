import unittest

from ogmkdev import diagnostics
from ogmkdev.languages import Detection
from ogmkdev.lexers import typescript_lexer as TL
from ogmkdev.parsers import javascript as J

TYPESCRIPT = [
    "let x: number = 1, y: string; const z!: Map<string, number[]>;",
    "interface Shape<T extends object = {}> extends Base<T>, Other { readonly id: number; name?: string; "
    "[key: string]: unknown; (x: number): string; new (x: number): Shape<T>; method<U>(a: U): void; "
    "get size(): number; }",
    "type Pair<A, B = A> = [A, B?, ...C[]] | { a: A; b: B } | ((x: A) => B) | keyof typeof obj;",
    "type Cond<T> = T extends string ? 'str' : T extends (infer U)[] ? U : never;",
    "type Mapped<T> = { readonly [K in keyof T]?: T[K] }; type Strip<T> = { -readonly [K in keyof T]-?: T[K] };",
    "type Tpl = `prefix-${string}`; type Pred = (x: unknown) => x is string;",
    "enum Color { Red, Green = 'g', Blue = 1 << 2 } const enum Dir { Up }",
    "namespace Shapes.Round { export class Circle {} } declare namespace NodeJS { interface Global {} }",
    "declare module 'x' { export const y: number; } declare global { interface Window { app: App } }",
    "declare function f(a: string): void; declare const g: number; export declare class K { m(): void }",
    "function over(a: string): void; function over(a: number): void; function over(a: any) {}",
    "class C<T> extends B<T> implements I, J<T> { private readonly x: number = 1; static #p?: string; "
    "protected abstract m(): void; constructor(public a: number, private b?: string) { super(); } "
    "static { } [k: string]: any; declare q: number; override r!: T; }",
    "abstract class A { abstract f(): number; }",
    "@sealed @log('x') class D { @observable value = 1; @dec() method(@inject() p: number) {} }",
    "let v = obj as unknown as Record<string, number>; let w = val satisfies Config; "
    "const cfg = { a: 1 } as const; let n = maybe!.field!;",
    "let r = identity<string>('a'); let arr = new Map<string, number>(); tag<T>`x`;",
    "const f = <T,>(x: T): T => x; const g = async <T>(x: T): Promise<T> => x; "
    "const h = (a: number, b = 2): number => a + b;",
    "let cast = <string>value; let typed = (value as any).x;",
    "import type { A, B } from 'mod'; import { type C, D } from 'mod2'; import E = require('e'); "
    "import F = G.H; export type { A }; export = E;",
    "export default interface I {} export as namespace UMD;",
    "function assertIsString(val: any): asserts val is string {} function isS(this: Window, x): this is Foo {}",
    "let u: unique symbol; let k: keyof T; let t: readonly string[]; let idx: T['a' | 'b']; "
    "let imp: import('mod').Thing<number>;",
    "let fn: new () => Foo; let ac: abstract new () => Bar; let nn: -1 | 'a' | true | null | undefined | void;",
    "class G<in out T, const U> {}",
    "let opt = a?.b!.c?.(d)!;",
    "for (const x of xs as number[]) {}",
    "let big: bigint = 10n;",
    "label: for (let i: number = 0; i < 3; i++) { break label; }",
    "let g2: <R, A extends any[]>(fn: (...args: A) => R) => R;",
    "class Holder { static snapshot(): <R>(f: () => R) => R; m?: () => void; }",
]

TSX = [
    "const el = <div className='a' id={x}>Don't <b>{y}</b>{/* c */}</div>;",
    "const f = <T,>(x: T) => <span>{x}</span>;",
    "const frag = <><p>one</p><p>two</p></>;",
    "const sp = <Comp {...props} data-test='1' aria-label=\"x\" xlink:href='#a' />;",
    "const m = <Foo.Bar.Baz prop={<i />} />;",
    "function App(): JSX.Element { return <main>{items.map((i) => <li key={i.id}>{i.name as string}</li>)}</main>; }",
    "const typed: Props = <Button<string> onClick={() => null} />;",
]

JAVASCRIPT_WITH_JSX = [
    "const a = <div>Don't stop</div>;",
    "export default () => <Layout title='x'><Page /></Layout>;",
    "const b = cond ? <A /> : <B />;",
    "const c = <a href=\"x\">{ /* just a comment */ }</a>;",
    "const d = <p>{list.map(x => <i key={x}>{x}</i>)}</p>;",
]


class TypeScriptAcceptsTests(unittest.TestCase):
    def test_typescript_programs_parse(self):
        for source in TYPESCRIPT:
            with self.subTest(source=source):
                J.parse(source, typed=True, jsx=False)

    def test_tsx_programs_parse(self):
        for source in TSX:
            with self.subTest(source=source):
                J.parse(source, typed=True, jsx=True)

    def test_javascript_with_jsx_parses(self):
        for source in JAVASCRIPT_WITH_JSX:
            with self.subTest(source=source):
                J.parse(source)


class TypeScriptErrorTests(unittest.TestCase):
    def assertError(self, source, line, column, fragment, typed=True, jsx=False):
        with self.assertRaises(J.ParseError) as caught:
            J.parse(source, typed=typed, jsx=jsx)
        error = caught.exception
        self.assertEqual((error.line, error.column), (line, column), error.message)
        self.assertIn(fragment, error.message)

    def test_missing_type_after_colon(self):
        self.assertError("let x: = 1;", 1, 8, "expected a type, found '='")

    def test_missing_type_in_alias(self):
        self.assertError("type T = ;", 1, 10, "expected a type, found ';'")

    def test_enum_initializer_missing(self):
        self.assertError("enum E { A = }", 1, 14, "unexpected '}'")

    def test_jsx_closing_tag_must_match(self):
        self.assertError("let v = <div>hi</span>;", 1, 18, "closing tag '</span>' does not match '<div>'",
                         typed=True, jsx=True)

    def test_type_assertion_is_not_jsx_in_typescript_files(self):
        # in a .ts file '<div>' is a type assertion, and '</div>' then reads as a comparison and a regexp
        self.assertError("let v = <div>hi</div>;", 1, 17, "regular expression", typed=True, jsx=False)


class TreeTests(unittest.TestCase):
    def kinds(self, node):
        return [child.kind for child in node.children]

    def find(self, tree, kind):
        return [node for node in tree.walk() if node.kind == kind]

    def test_jsx_element_names_attributes_and_children(self):
        tree = J.parse("const el = <a.b x='1' {...rest}>t{y}<c /></a.b>;", typed=True, jsx=True)
        element = self.find(tree, "JSXElement")[0]
        self.assertEqual(element.text, "a.b")
        self.assertEqual(self.kinds(element)[:3], ["JSXName", "JSXAttribute", "JSXSpreadAttribute"])
        self.assertIn("JSXText", self.kinds(element))
        self.assertIn("JSXExpressionContainer", self.kinds(element))
        self.assertEqual([n.text for n in self.find(tree, "JSXElement")], ["a.b", "c"])

    def test_fragment_is_a_fragment(self):
        tree = J.parse("const f = <><p>x</p></>;", typed=True, jsx=True)
        self.assertEqual(len(self.find(tree, "JSXFragment")), 1)

    def test_hyphenated_attribute_names_are_one_name(self):
        tree = J.parse("const e = <a data-x-y='1' />;", typed=True, jsx=True)
        names = [n.text for n in self.find(tree, "JSXName")]
        self.assertIn("data-x-y", names)

    def test_generic_arrow_has_type_parameters_before_the_body(self):
        arrow = self.find(J.parse("const f = <T,>(x: T): T => x;", typed=True, jsx=True), "ArrowFunction")[0]
        self.assertEqual(self.kinds(arrow), ["FormalParameters", "TypeParameters", "TypeReference", "Identifier"])

    def test_declarator_has_its_annotation_and_initializer(self):
        declarator = self.find(J.parse("let x: number = 1;", typed=True), "VariableDeclarator")[0]
        self.assertEqual(self.kinds(declarator), ["Identifier", "TypeKeyword", "Literal"])
        self.assertIn("init", declarator.flags)

    def test_interface_members(self):
        tree = J.parse("interface I { a: string; m(): void; [k: string]: any; new (): I; get g(): number; }",
                       typed=True)
        literal = self.find(tree, "TypeLiteral")[0]
        self.assertEqual(self.kinds(literal),
                         ["PropertySignature", "MethodSignature", "IndexSignature", "ConstructSignature",
                          "MethodSignature"])

    def test_as_satisfies_and_non_null(self):
        tree = J.parse("x as T; y satisfies U; z!;", typed=True)
        self.assertEqual(len(self.find(tree, "AsExpression")), 1)
        self.assertEqual(len(self.find(tree, "SatisfiesExpression")), 1)
        self.assertEqual(len(self.find(tree, "NonNullExpression")), 1)

    def test_enum_members_and_const(self):
        enum = self.find(J.parse("const enum E { A, B = 2 }", typed=True), "EnumDeclaration")[0]
        self.assertEqual(self.kinds(enum), ["Identifier", "EnumMember", "EnumMember"])
        self.assertIn("const", enum.flags)

    def test_declare_wraps_the_declaration(self):
        ambient = self.find(J.parse("declare const v: number;", typed=True), "AmbientDeclaration")[0]
        self.assertEqual(self.kinds(ambient), ["VariableDeclaration"])

    def test_generic_call_keeps_its_type_arguments(self):
        call = self.find(J.parse("f<string>(x);", typed=True), "CallExpression")[0]
        self.assertEqual(self.kinds(call)[1], "TypeArguments")

    def test_less_than_is_still_a_comparison_in_typed_code(self):
        comparison = self.find(J.parse("a < b;", typed=True), "BinaryExpression")[0]
        self.assertEqual(comparison.text, "<")


class DiagnosticsByLanguageTests(unittest.TestCase):
    def analyze(self, text, language):
        return diagnostics.analyze(text, Detection(language, None, None, "extension"))

    def test_jsx_in_javascript_is_not_an_error(self):
        self.assertEqual(self.analyze("let a = <div>Don't</div>;", "ecmascript"), [])

    def test_jsx_in_tsx_is_not_an_error(self):
        self.assertEqual(self.analyze("let a = <div>Don't</div>;", "tsx"), [])

    def test_jsx_is_not_read_in_typescript_files(self):
        found = self.analyze("let a = <div>x</div>;", "typescript")
        self.assertEqual([d.code for d in found], ["js-lexical"])  # the regexp that '</div>' opens is unterminated

    def test_typescript_types_are_checked(self):
        found = self.analyze("let x: = 1;\n", "typescript")
        self.assertEqual([(d.line, d.column, d.code) for d in found], [(1, 8, "js-syntax")])

    def test_a_malformed_token_is_a_lexical_error(self):
        found = self.analyze("let s = 'open\n", "typescript")
        self.assertEqual([d.code for d in found], ["js-lexical"])


class TypeScriptLexerTests(unittest.TestCase):
    def test_words_of_typescript_are_keywords_and_predefined_types_are_types(self):
        tokens = [(t.kind, "type T = string;"[t.start:t.end]) for t in TL.tokenize("type T = string;")]
        self.assertEqual(tokens, [("keyword", "type"), ("identifier", "T"), ("punctuator", "="),
                                  ("type", "string"), ("punctuator", ";")])

    def test_error_tokens_are_left_out(self):
        self.assertTrue(all(t.kind != "error" for t in TL.tokenize("<p>Don't</p>")))


if __name__ == "__main__":
    unittest.main()
