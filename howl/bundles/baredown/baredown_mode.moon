-- BareDown mode: the lexer of baredown_lexer, and the comment syntax of a BareDown comment line
{
  lexer: bundle_load('baredown_lexer')
  word_pattern: r'\\b\\w[\\w\\d_-]+\\b'

  comment_syntax: '%%'

  auto_pairs: {
    '[': ']'
    '|': '|'
    '"': '"'
  }
}
