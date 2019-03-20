import re
import string
import bisect
from collections import namedtuple

try:
    regex_type = re.Pattern
except AttributeError:
    try:
        regex_type = re.RegexObject
    except AttributeError:
        regex_type = type(re.compile(''))

def escape(s):
    return repr(s)[1:-1]

def regex_matcher(regex):
    def match(text, pos):
        match = regex.match(text, pos)
        if match:
            return match.end()
        else:
            return None
    return match

def literal_matcher(literal):
    size = len(literal)
    def match(text, pos):
        left = len(text) - pos
        if left < size: return None
        if text[pos:pos+size] == literal:
            return pos + size
        else:
            return None
    return match

def never_matcher(text, pos):
    return None

def always_matcher(text, pos):
    return pos + 1

class Rule(object):
    def __init__(self, name, matcher, value=None, ignore=False):
        if not isinstance(name, str):
            raise TypeError('Expected string for name, got {!r}'.format(type(name)))
        if not name:
            raise ValueError('Expected non-empty name for rule')
        if not callable(matcher):
            raise ValueError('Expected a callable for matcher')
        if value and not callable(value):
            raise ValueError('Expected a callable for value if specified')

        self.name = name
        self.matcher = matcher
        self.value = value
        self.ignore = bool(ignore)

    def __str__(self):
        return '{!r}'.format(self.name)

    def __repr__(self):
        return 'Rule({!r})'.format(self.name)

# Special rules for begin and end
Begin = Rule('begin-of-file', never_matcher)
End = Rule('end-of-file', never_matcher)

def matcher_from_pattern(pattern):
    if isinstance(pattern, str):
        # Compile strings to regex
        regex = re.compile(pattern, re.ASCII)
        return regex_matcher(regex)
    elif isinstance(pattern, regex_type):
        # Already compiled regex
        return regex_matcher(pattern)
    elif callable(pattern):
        # Custom matcher function
        return pattern
    else:
        raise TypeError('Invalid type for rule pattern {!r}'.format(type(pattern)))

class NonAscii:
    def __repr__(self):
        return 'NonAscii()'

class Lexer(object):
    def __init__(self):
        self.global_rules = []
        self.prefix_rules = {}
        self.non_ascii_rules = []

    def add_rule(self, rule, prefix=None):
        if prefix:
            for pre in prefix:
                if isinstance(pre, str):
                    if len(pre) > 1:
                        raise ValueError('Prefixes must be single characters')
                    rules = self.prefix_rules.setdefault(pre, [])
                    rules.append(rule)
                elif isinstance(pre, NonAscii):
                    self.non_ascii_rules.push(rule)
        else:
            self.global_rules.append(rule)

    def rule(self, name, pattern, value=None, prefix=None):
        matcher = matcher_from_pattern(pattern)
        rule = Rule(name, matcher, value, ignore=False)
        self.add_rule(rule, prefix)

    def ignore(self, name, pattern, value=None, prefix=None):
        matcher = matcher_from_pattern(pattern)
        rule = Rule(name, matcher, value, ignore=True)
        self.add_rule(rule, prefix)

    def literal(self, *args):
        for literal in args:
            if not isinstance(literal, str):
                raise TypeError('Literals must be strings, got {!r}'.format(type(literal)))
            if not literal:
                raise ValueError('Empty literal')
            if len(literal) == 1:
                # Prefix match is full match
                matcher = always_matcher
            else:
                matcher = literal_matcher(literal)
            rule = Rule(literal, matcher)
            self.add_rule(rule, literal[0])

newline_pattern = re.compile('\n')

class SourceFile(object):
    def __init__(self, filename, text):
        self.filename = filename
        self.text = text
        self.length = len(text)
        self.breaks = None

    def find_breaks(self):
        if self.breaks:
            return self.breaks

        pos = 0
        breaks = [0]
        text = self.text
        while True:
            pos = text.find('\n', pos) + 1
            if pos == 0: break
            breaks.append(pos)
        self.breaks = breaks
        return breaks

    def line_col(self, offset):
        breaks = self.find_breaks()
        line = bisect.bisect_right(breaks, offset) - 1
        if line < len(breaks):
            column = offset - breaks[line]
        return line + 1, column + 1

    def begin(self):
        return Token(Begin, Span(self, 0, 0))

    def end(self):
        end = len(self.text)
        return Token(End, Span(self, end, end))

    def __repr__(self):
        return 'SourceFile({!r})'.format(self.filename)

class Span(object):
    __slots__ = ['source', 'begin', 'end']
    def __init__(self, source, begin, end):
        if begin < 0: raise ValueError('Span begin is negative')
        if end < 0: raise ValueError('Span end is negative')
        if begin > source.length: raise ValueError('Span begin is too large')
        if end > source.length: raise ValueError('Span end is too large')
        if end < begin: raise ValueError('Span end is lower than begin')

        self.source = source
        self.begin = begin
        self.end = end

    def __str__(self):
        max_print = 59 # 64 with quotes and ellipsis
        text = self.source.text
        begin, end = self.begin, self.end
        if end - begin > max_print:
            return repr(text[begin:begin+max_print]) + '...'
        else:
            return repr(text[begin:end])

    def __len__(self):
        return self.end - self.begin

    def __repr__(self):
        return 'Span({})'.format(str(self))

    def text(self):
        return self.source.text[self.begin:self.end]

    def line_col(self):
        return self.source.line_col(self.begin)

class Token(object):
    __slots__ = ['rule', 'span', 'value']
    def __init__(self, rule, span, value=None):
        self.rule = rule
        self.span = span
        self.value = value

    def __str__(self):
        rname = self.rule.name
        if len(self.span) == len(rname) and self.span.text() == rname:
            return repr(rname)
        elif len(self.span) > 0:
            return '{} {}'.format(escape(rname), self.span)
        else:
            return escape(rname)

    def __repr__(self):
        return 'Token({}, {})'.format(self, self.span)

    def line_col(self):
        return self.span.line_col()

class SourceLexer(object):
    def __init__(self, lexer, source):
        self.pos = 0
        self.lexer = lexer
        self.source = source

    def scan(self):
        pos = self.pos
        text = self.source.text
        length = len(text)
        lexer = self.lexer
        while pos < length:
            leading = text[pos]
            rules = lexer.prefix_rules.get(leading)

            value = None
            best_pos = pos
            best_rule = None
            best_value = None

            if rules:
                for rule in rules:
                    match = rule.matcher(text, pos)
                    if match:
                        if isinstance(match, tuple):
                            value = match[1]
                            match = match[0]
                        if not isinstance(match, int):
                            raise ValueError('Expected matcher to return the next position as int, got {!r}')
                        if match > best_pos:
                            best_pos = match
                            best_rule = rule
                            best_value = value

            for rule in lexer.global_rules:
                match = rule.matcher(text, pos)
                if match:
                    if isinstance(match, tuple):
                        value = match[1]
                        match = match[0]
                    if not isinstance(match, int):
                        raise ValueError('Expected matcher to return the next position as int')
                    if match > best_pos:
                        best_pos = match
                        best_rule = rule
                        best_value = value

            if ord(leading) > 128:
                for rule in lexer.non_ascii_rules:
                    match = rule.matcher(text, pos)
                    if match:
                        if isinstance(match, tuple):
                            value = match[1]
                            match = match[0]
                        if not isinstance(match, int):
                            raise ValueError('Expected matcher to return the next position as int')
                        if match > best_pos:
                            best_pos = match
                            best_rule = rule
                            best_value = value

            if best_rule == None:
                span = Span(self.source, pos, pos)
                raise ParseError(span, 'Unexpected character {!r}'.format(text[pos]))

            if best_rule.ignore:
                pos = best_pos
            else:
                self.pos = best_pos
                span = Span(self.source, pos, best_pos)
                token = Token(best_rule, span)
                return token

        return self.source.end()

