import sys
sys.path.append("..")

from parsette import parsette
import string

lexer = parsette.Lexer()

lexer.literal(*'()+-*/')
lexer.ignore('whitespace', '\s+', prefix=string.whitespace)
Number = lexer.rule('number', '[0-9]+', value=int)
Identifier = lexer.rule('identifier', '[A-Za-z_][A-Za-z0-9_]*', value=str)

calc = {
    '+': lambda a, b: a + b,
    '-': lambda a, b: a - b,
    '*': lambda a, b: a * b,
    '/': lambda a, b: a / b,
}

variables = { }

def parse_atom(p):
    if p.accept('('):
        res = parse_expr(p)
        p.require(')', 'for closing \'(\'')
    elif p.accept(Number):
        res = p.prev_token.value
    elif p.accept(Identifier):
        res = variables[p.prev_token.value]
    elif p.accept('+'):
        res = parse_expr(p)
    elif p.accept('-'):
        res = -parse_expr(p)
    else:
        p.fail('Expected an expression')
    return res

def parse_factor(p):
    lhs = parse_atom(p)
    while p.accept(['*', '/']):
        op = p.prev_token.text
        rhs = parse_atom(p)
        lhs = calc[op](lhs, rhs)

def parse_term(p):
    lhs = parse_atom(p)
    while p.accept(['+', '-']):
        op = p.prev_token.text
        rhs = parse_factor(p)
        lhs = calc[op](lhs, rhs)

def parse_expr(p):
    expr = parse_term(p)
    require(parsette.End)
    return expr

def parse(expr):
    p = parsette.Parser(lexer, expr)
    return parse_expr(p)


source = parsette.SourceFile('<test>', '1 + 2 * (3 + -4)')
token = source.begin()
sl = parsette.SourceLexer(lexer, source)
while token.rule != parsette.End:
    token = sl.scan()
    print(token)

# print(parse('1 + 2 * (3 + -4)'))

