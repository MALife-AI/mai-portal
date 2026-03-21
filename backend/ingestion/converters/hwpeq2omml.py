"""한컴 수식 스크립트 → OMML(Office Math Markup Language) 변환기

한컴오피스의 수식 편집기 문법을 파싱하여 DOCX에서 사용하는 OMML XML로 변환합니다.

지원 문법:
  - 분수: A over B
  - 위첨자: A^B, A^(B), A^{B}
  - 아래첨자: A_B, A_{B}
  - 그리스 문자: alpha, beta, gamma, ...
  - 합/곱: SUM from A to B, PROD from A to B
  - 대괄호: LEFT ( ... RIGHT )
  - 케이스: cases{ A ## B }
  - 악센트: bar, hat, dot, ddot, tilde, vec
  - 연산자: times, cdot, pm, mp, leq, geq, neq, ...
  - 공백: ~(보통), `(좁은), ``(아주좁은)
  - 따옴표 텍스트: "text"
  - rm (로만체)
  - sqrt (제곱근)
"""

import re
import xml.etree.ElementTree as ET

# OMML 네임스페이스
M_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def _m(tag):
    return f'{{{M_NS}}}{tag}'


def _w(tag):
    return f'{{{W_NS}}}{tag}'


# 그리스 문자 매핑
GREEK = {
    'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε',
    'zeta': 'ζ', 'eta': 'η', 'theta': 'θ', 'iota': 'ι', 'kappa': 'κ',
    'lambda': 'λ', 'mu': 'μ', 'nu': 'ν', 'xi': 'ξ', 'omicron': 'ο',
    'pi': 'π', 'rho': 'ρ', 'sigma': 'σ', 'tau': 'τ', 'upsilon': 'υ',
    'phi': 'φ', 'chi': 'χ', 'psi': 'ψ', 'omega': 'ω',
    'Alpha': 'Α', 'Beta': 'Β', 'Gamma': 'Γ', 'Delta': 'Δ', 'Epsilon': 'Ε',
    'Zeta': 'Ζ', 'Eta': 'Η', 'Theta': 'Θ', 'Iota': 'Ι', 'Kappa': 'Κ',
    'Lambda': 'Λ', 'Mu': 'Μ', 'Nu': 'Ν', 'Xi': 'Ξ', 'Omicron': 'Ο',
    'Pi': 'Π', 'Rho': 'Ρ', 'Sigma': 'Σ', 'Tau': 'Τ', 'Upsilon': 'Υ',
    'Phi': 'Φ', 'Chi': 'Χ', 'Psi': 'Ψ', 'Omega': 'Ω',
    'inf': '∞', 'infty': '∞', 'partial': '∂',
}

# 연산자 매핑
OPERATORS = {
    'times': '×', 'cdot': '⋅', 'pm': '±', 'mp': '∓',
    'leq': '≤', 'geq': '≥', 'neq': '≠', 'approx': '≈',
    'equiv': '≡', 'propto': '∝', 'forall': '∀', 'exists': '∃',
    'nabla': '∇', 'in': '∈', 'notin': '∉',
    'subset': '⊂', 'supset': '⊃', 'cup': '∪', 'cap': '∩',
    'vee': '∨', 'wedge': '∧', 'oplus': '⊕', 'otimes': '⊗',
    'rightarrow': '→', 'leftarrow': '←', 'Rightarrow': '⇒',
    'Leftarrow': '⇐', 'leftrightarrow': '↔',
    'therefore': '∴', 'because': '∵',
}

# 악센트 매핑 (OMML accent character)
ACCENTS = {
    'bar': '\u0304',      # combining macron
    'hat': '\u0302',      # combining circumflex
    'dot': '\u0307',      # combining dot above
    'ddot': '\u0308',     # combining diaeresis
    'tilde': '\u0303',    # combining tilde
    'vec': '\u20D7',      # combining right arrow above
    'ddota': '\u0308',    # alias
    'check': '\u030C',    # combining caron
}

# n-ary 연산자 매핑
NARY_OPS = {
    'SUM': '∑', 'PROD': '∏', 'INT': '∫',
    'sum': '∑', 'prod': '∏', 'int': '∫',
}

# 괄호 매핑
BRACKET_MAP = {
    '(': '(', ')': ')',
    '[': '[', ']': ']',
    '{': '{', '}': '}',  # note: literal braces in HWP eq
    '|': '|',
    'langle': '⟨', 'rangle': '⟩',
}


class Token:
    def __init__(self, type_, value):
        self.type = type_
        self.value = value

    def __repr__(self):
        return f'Token({self.type}, {self.value!r})'


class HwpEqTokenizer:
    """한컴 수식 스크립트 토크나이저"""

    KEYWORDS = {
        'over', 'from', 'to', 'cases', 'sqrt', 'rm',
        'LEFT', 'RIGHT', 'left', 'right',
        'MAX', 'Max', 'max', 'MIN', 'Min', 'min',
    } | set(ACCENTS.keys()) | set(NARY_OPS.keys()) | set(OPERATORS.keys()) | set(GREEK.keys())

    def __init__(self, script):
        self.script = script
        self.pos = 0
        self.tokens = []

    def tokenize(self):
        while self.pos < len(self.script):
            ch = self.script[self.pos]

            # 공백 종류
            if ch == '~':
                self.tokens.append(Token('SPACE', ' '))
                self.pos += 1
            elif ch == '`':
                self.tokens.append(Token('SPACE', '\u2009'))  # thin space
                self.pos += 1
            elif ch in ' \t':
                self.pos += 1  # 일반 공백은 무시
            elif ch == '\n' or ch == '\r':
                self.pos += 1
            # 따옴표 문자열
            elif ch == '"':
                self.pos += 1
                text = []
                while self.pos < len(self.script) and self.script[self.pos] != '"':
                    text.append(self.script[self.pos])
                    self.pos += 1
                if self.pos < len(self.script):
                    self.pos += 1  # closing quote
                self.tokens.append(Token('TEXT', ''.join(text)))
            # 중괄호 그룹
            elif ch == '{':
                self.tokens.append(Token('LBRACE', '{'))
                self.pos += 1
            elif ch == '}':
                self.tokens.append(Token('RBRACE', '}'))
                self.pos += 1
            # 괄호
            elif ch == '(':
                self.tokens.append(Token('LPAREN', '('))
                self.pos += 1
            elif ch == ')':
                self.tokens.append(Token('RPAREN', ')'))
                self.pos += 1
            elif ch == '[':
                self.tokens.append(Token('LBRACKET', '['))
                self.pos += 1
            elif ch == ']':
                self.tokens.append(Token('RBRACKET', ']'))
                self.pos += 1
            # 위/아래 첨자
            elif ch == '^':
                self.tokens.append(Token('SUP', '^'))
                self.pos += 1
            elif ch == '_':
                self.tokens.append(Token('SUB', '_'))
                self.pos += 1
            # ## (cases 구분자)
            elif ch == '#' and self.pos + 1 < len(self.script) and self.script[self.pos + 1] == '#':
                self.tokens.append(Token('CASE_SEP', '##'))
                self.pos += 2
            elif ch == '#':
                self.pos += 1  # skip single #
            # = , + - 등 단일 연산자
            elif ch in '=+-><!&':
                self.tokens.append(Token('CHAR', ch))
                self.pos += 1
            elif ch == '-':
                self.tokens.append(Token('CHAR', '−'))
                self.pos += 1
            elif ch == ',':
                self.tokens.append(Token('CHAR', ','))
                self.pos += 1
            elif ch == ';':
                self.tokens.append(Token('CHAR', ';'))
                self.pos += 1
            elif ch == ':':
                self.tokens.append(Token('CHAR', ':'))
                self.pos += 1
            elif ch == '|':
                self.tokens.append(Token('CHAR', '|'))
                self.pos += 1
            # 식별자 / 키워드
            elif ch.isalpha() or ch in 'γβαδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩ':
                word = self._read_word()
                if word in NARY_OPS:
                    self.tokens.append(Token('NARY', word))
                elif word == 'over':
                    self.tokens.append(Token('OVER', 'over'))
                elif word in ('from',):
                    self.tokens.append(Token('FROM', 'from'))
                elif word in ('to',):
                    self.tokens.append(Token('TO', 'to'))
                elif word == 'cases':
                    self.tokens.append(Token('CASES', 'cases'))
                elif word == 'sqrt':
                    self.tokens.append(Token('SQRT', 'sqrt'))
                elif word in ('rm',):
                    self.tokens.append(Token('RM', 'rm'))
                elif word in ('LEFT', 'left'):
                    self.tokens.append(Token('LEFT', word))
                elif word in ('RIGHT', 'right'):
                    self.tokens.append(Token('RIGHT', word))
                elif word in ACCENTS:
                    self.tokens.append(Token('ACCENT', word))
                elif word in OPERATORS:
                    self.tokens.append(Token('CHAR', OPERATORS[word]))
                elif word in GREEK:
                    self.tokens.append(Token('CHAR', GREEK[word]))
                elif word in ('MAX', 'Max', 'max', 'MIN', 'Min', 'min'):
                    self.tokens.append(Token('FUNC', word))
                else:
                    # 일반 식별자 - 문자별로 분리
                    for c in word:
                        self.tokens.append(Token('CHAR', c))
            elif ch.isdigit():
                num = self._read_number()
                for c in num:
                    self.tokens.append(Token('CHAR', c))
            elif ch in '˥':  # 한컴 특수 문자 (꺾인 괄호 등)
                self.tokens.append(Token('CHAR', '⌉'))
                self.pos += 1
            elif ch in '｛':
                self.tokens.append(Token('CHAR', '{'))
                self.pos += 1
            elif ch in '｝':
                self.tokens.append(Token('CHAR', '}'))
                self.pos += 1
            elif ch == '＝':
                self.tokens.append(Token('CHAR', '='))
                self.pos += 1
            elif ch == '　':  # 전각 공백
                self.tokens.append(Token('SPACE', ' '))
                self.pos += 1
            elif ch == '×':
                self.tokens.append(Token('CHAR', '×'))
                self.pos += 1
            elif ch == '\'':
                self.tokens.append(Token('CHAR', '′'))
                self.pos += 1
            elif ch == '.':
                self.tokens.append(Token('CHAR', '.'))
                self.pos += 1
            else:
                # 기타 유니코드 문자
                self.tokens.append(Token('CHAR', ch))
                self.pos += 1

        return self.tokens

    def _read_word(self):
        start = self.pos
        while self.pos < len(self.script) and (self.script[self.pos].isalpha() or self.script[self.pos] in '_*'):
            self.pos += 1
        return self.script[start:self.pos]

    def _read_number(self):
        start = self.pos
        while self.pos < len(self.script) and (self.script[self.pos].isdigit() or self.script[self.pos] == '.'):
            self.pos += 1
        return self.script[start:self.pos]


class HwpEqParser:
    """한컴 수식 토큰 → OMML XML 트리 파서"""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, type_):
        tok = self.peek()
        if tok and tok.type == type_:
            return self.advance()
        return None

    def parse(self):
        """전체 수식을 파싱하여 OMML oMath 요소 반환"""
        omath = ET.Element(_m('oMath'))
        self._parse_expression(omath)
        return omath

    def _parse_expression(self, parent):
        """표현식 파싱 (over 연산 포함)"""
        while self.pos < len(self.tokens):
            tok = self.peek()
            if tok is None:
                break
            if tok.type in ('RBRACE', 'RPAREN', 'RBRACKET', 'CASE_SEP', 'TO', 'RIGHT'):
                break

            self._parse_item(parent)

    def _parse_item(self, parent):
        """단일 항목 파싱"""
        tok = self.peek()
        if tok is None:
            return

        # 먼저 기본 요소를 파싱
        elem = self._parse_primary()
        if elem is None:
            return

        # over 체크
        if self.peek() and self.peek().type == 'OVER':
            self.advance()  # consume 'over'
            frac = ET.SubElement(parent, _m('f'))
            # fraction properties
            fPr = ET.SubElement(frac, _m('fPr'))
            # numerator
            num = ET.SubElement(frac, _m('num'))
            num.append(elem)
            # denominator
            den = ET.SubElement(frac, _m('den'))
            den_elem = self._parse_primary()
            if den_elem is not None:
                den.append(den_elem)
            # over 이후 다시 over 체크 (연쇄)
            return

        parent.append(elem)

        # 위/아래 첨자 체크
        self._parse_scripts(parent)

    def _parse_primary(self):
        """기본 요소 파싱"""
        tok = self.peek()
        if tok is None:
            return None

        if tok.type == 'LBRACE':
            return self._parse_brace_group()
        elif tok.type == 'LPAREN':
            return self._parse_paren_group()
        elif tok.type == 'CHAR':
            self.advance()
            return self._make_run(tok.value)
        elif tok.type == 'TEXT':
            self.advance()
            return self._make_run(tok.value)
        elif tok.type == 'SPACE':
            self.advance()
            return self._make_run(tok.value)
        elif tok.type == 'NARY':
            return self._parse_nary()
        elif tok.type == 'CASES':
            return self._parse_cases()
        elif tok.type == 'SQRT':
            return self._parse_sqrt()
        elif tok.type == 'ACCENT':
            return self._parse_accent()
        elif tok.type == 'LEFT':
            return self._parse_delimiters()
        elif tok.type == 'RM':
            self.advance()
            return self._parse_rm()
        elif tok.type == 'FUNC':
            self.advance()
            return self._make_run(tok.value)
        elif tok.type in ('SUP', 'SUB'):
            # orphan sup/sub - create empty base
            return self._make_run('')
        elif tok.type == 'FROM':
            self.advance()
            return self._make_run('')
        elif tok.type == 'OVER':
            return self._make_run('')
        else:
            self.advance()
            return self._make_run(tok.value)

    def _parse_scripts(self, parent):
        """위첨자/아래첨자 처리"""
        while self.peek() and self.peek().type in ('SUP', 'SUB'):
            tok = self.peek()

            # parent에서 마지막 요소를 base로 사용
            if len(parent) == 0:
                base = self._make_run('')
            else:
                base = parent[-1]
                parent.remove(base)

            if tok.type == 'SUB' and self.pos + 1 < len(self.tokens):
                self.advance()  # consume _
                sub_elem = self._parse_script_arg()

                # 아래첨자 다음에 위첨자가 올 수 있음
                if self.peek() and self.peek().type == 'SUP':
                    self.advance()  # consume ^
                    sup_elem = self._parse_script_arg()
                    # sSubSup
                    ssubsup = ET.SubElement(parent, _m('sSubSup'))
                    e = ET.SubElement(ssubsup, _m('e'))
                    e.append(base)
                    sub_e = ET.SubElement(ssubsup, _m('sub'))
                    sub_e.append(sub_elem)
                    sup_e = ET.SubElement(ssubsup, _m('sup'))
                    sup_e.append(sup_elem)
                else:
                    ssub = ET.SubElement(parent, _m('sSub'))
                    e = ET.SubElement(ssub, _m('e'))
                    e.append(base)
                    sub_e = ET.SubElement(ssub, _m('sub'))
                    sub_e.append(sub_elem)

            elif tok.type == 'SUP':
                self.advance()  # consume ^
                sup_elem = self._parse_script_arg()
                ssup = ET.SubElement(parent, _m('sSup'))
                e = ET.SubElement(ssup, _m('e'))
                e.append(base)
                sup_e = ET.SubElement(ssup, _m('sup'))
                sup_e.append(sup_elem)

    def _parse_script_arg(self):
        """첨자 인수 파싱 (단일 문자, 괄호 그룹, 또는 중괄호 그룹)"""
        tok = self.peek()
        if tok is None:
            return self._make_run('')

        if tok.type == 'LBRACE':
            return self._parse_brace_group()
        elif tok.type == 'LPAREN':
            return self._parse_paren_group()
        elif tok.type == 'CHAR':
            self.advance()
            # 연속된 문자/숫자를 하나로
            text = tok.value
            while self.peek() and self.peek().type == 'CHAR' and self.peek().value not in '=+-><!,;:| ×⋅±∓≤≥≠≈':
                text += self.advance().value
            return self._make_run(text)
        elif tok.type == 'ACCENT':
            return self._parse_accent()
        else:
            self.advance()
            return self._make_run(tok.value)

    def _parse_brace_group(self):
        """{ ... } 그룹 파싱"""
        self.advance()  # consume {
        group = ET.Element(_m('r'))  # placeholder
        # 실제로는 여러 요소를 포함할 수 있으므로 wrapper 사용
        group = ET.Element(_m('e'))  # use 'e' as generic container temporarily

        # parse until }
        elements = []
        while self.pos < len(self.tokens):
            tok = self.peek()
            if tok is None or tok.type == 'RBRACE':
                break
            if tok.type == 'OVER':
                # fraction
                self.advance()  # consume over
                frac = ET.Element(_m('f'))
                fPr = ET.SubElement(frac, _m('fPr'))
                num = ET.SubElement(frac, _m('num'))
                for e in elements:
                    num.append(e)
                elements = []
                den = ET.SubElement(frac, _m('den'))
                # parse denominator until }
                while self.pos < len(self.tokens):
                    t2 = self.peek()
                    if t2 is None or t2.type == 'RBRACE':
                        break
                    self._parse_item(den)
                elements = [frac]
                break
            else:
                self._parse_item(group)
                # move children from group to elements
                while len(group) > len(elements):
                    elements.append(group[len(elements)])

        self.expect('RBRACE')  # consume }

        # 결과 반환
        if len(elements) == 1:
            return elements[0]
        else:
            # 여러 요소를 하나로 묶기 위해 container 사용
            container = ET.Element(_m('oMath'))
            for e in elements:
                container.append(e)
            return container

    def _parse_paren_group(self):
        """( ... ) 그룹 파싱 - 괄호는 표시하지 않고 내용만"""
        self.advance()  # consume (
        container = ET.Element(_m('oMath'))

        while self.pos < len(self.tokens):
            tok = self.peek()
            if tok is None or tok.type == 'RPAREN':
                break
            self._parse_item(container)

        self.expect('RPAREN')

        if len(container) == 1:
            return container[0]
        return container

    def _parse_nary(self):
        """SUM, PROD, INT 등 n-ary 연산자"""
        tok = self.advance()
        char = NARY_OPS.get(tok.value, '∑')

        nary = ET.Element(_m('nary'))
        naryPr = ET.SubElement(nary, _m('naryPr'))
        chr_el = ET.SubElement(naryPr, _m('chr'))
        chr_el.set(_m('val'), char)

        sub = ET.SubElement(nary, _m('sub'))
        sup = ET.SubElement(nary, _m('sup'))
        e = ET.SubElement(nary, _m('e'))

        # from ... to ... 파싱
        if self.peek() and self.peek().type == 'FROM':
            self.advance()
            self._parse_nary_limit(sub)

        if self.peek() and self.peek().type == 'TO':
            self.advance()
            self._parse_nary_limit(sup)

        # body
        if self.peek() and self.peek().type == 'LBRACE':
            body = self._parse_brace_group()
            e.append(body)
        else:
            # parse one item
            elem = self._parse_primary()
            if elem is not None:
                e.append(elem)

        return nary

    def _parse_nary_limit(self, parent):
        """n-ary 한계값 파싱"""
        tok = self.peek()
        if tok is None:
            return
        if tok.type == 'LBRACE':
            elem = self._parse_brace_group()
            parent.append(elem)
        else:
            elem = self._parse_primary()
            if elem is not None:
                parent.append(elem)
            # scripts
            self._parse_scripts(parent)

    def _parse_cases(self):
        """cases{ ... ## ... } 파싱"""
        self.advance()  # consume 'cases'
        self.expect('LBRACE')

        # cases 각 행 수집
        rows = []
        current_row = ET.Element(_m('e'))

        while self.pos < len(self.tokens):
            tok = self.peek()
            if tok is None or tok.type == 'RBRACE':
                break
            if tok.type == 'CASE_SEP':
                self.advance()
                rows.append(current_row)
                current_row = ET.Element(_m('e'))
            else:
                self._parse_item(current_row)

        rows.append(current_row)
        self.expect('RBRACE')

        # OMML: 왼쪽 중괄호 + 행렬로 표현
        d = ET.Element(_m('d'))
        dPr = ET.SubElement(d, _m('dPr'))
        begChr = ET.SubElement(dPr, _m('begChr'))
        begChr.set(_m('val'), '{')
        endChr = ET.SubElement(dPr, _m('endChr'))
        endChr.set(_m('val'), '')

        e = ET.SubElement(d, _m('e'))

        # 행렬 (m:m)
        mat = ET.SubElement(e, _m('m'))
        for row_elem in rows:
            mr = ET.SubElement(mat, _m('mr'))
            me = ET.SubElement(mr, _m('e'))
            for child in list(row_elem):
                me.append(child)

        return d

    def _parse_sqrt(self):
        """sqrt 파싱"""
        self.advance()  # consume sqrt
        rad = ET.Element(_m('rad'))
        radPr = ET.SubElement(rad, _m('radPr'))
        degHide = ET.SubElement(radPr, _m('degHide'))
        degHide.set(_m('val'), '1')
        deg = ET.SubElement(rad, _m('deg'))
        e = ET.SubElement(rad, _m('e'))

        elem = self._parse_primary()
        if elem is not None:
            e.append(elem)

        return rad

    def _parse_accent(self):
        """bar, hat, dot 등 악센트"""
        tok = self.advance()
        acc_char = ACCENTS.get(tok.value, '\u0304')

        acc = ET.Element(_m('acc'))
        accPr = ET.SubElement(acc, _m('accPr'))
        chr_el = ET.SubElement(accPr, _m('chr'))
        chr_el.set(_m('val'), acc_char)
        e = ET.SubElement(acc, _m('e'))

        elem = self._parse_primary()
        if elem is not None:
            e.append(elem)

        return acc

    def _parse_delimiters(self):
        """LEFT ... RIGHT 괄호"""
        self.advance()  # consume LEFT

        # 여는 괄호
        open_char = '('
        tok = self.peek()
        if tok and tok.type in ('LPAREN', 'LBRACKET', 'CHAR'):
            self.advance()
            if tok.type == 'LPAREN':
                open_char = '('
            elif tok.type == 'LBRACKET':
                open_char = '['
            elif tok.value in BRACKET_MAP:
                open_char = BRACKET_MAP[tok.value]
            else:
                open_char = tok.value

        d = ET.Element(_m('d'))
        dPr = ET.SubElement(d, _m('dPr'))
        begChr = ET.SubElement(dPr, _m('begChr'))
        begChr.set(_m('val'), open_char)

        e = ET.SubElement(d, _m('e'))

        while self.pos < len(self.tokens):
            tok = self.peek()
            if tok is None:
                break
            if tok.type == 'RIGHT':
                self.advance()
                # 닫는 괄호
                close_tok = self.peek()
                close_char = ')'
                if close_tok and close_tok.type in ('RPAREN', 'RBRACKET', 'CHAR'):
                    self.advance()
                    if close_tok.type == 'RPAREN':
                        close_char = ')'
                    elif close_tok.type == 'RBRACKET':
                        close_char = ']'
                    elif close_tok.value in BRACKET_MAP:
                        close_char = BRACKET_MAP[close_tok.value]
                    else:
                        close_char = close_tok.value
                endChr = ET.SubElement(dPr, _m('endChr'))
                endChr.set(_m('val'), close_char)
                break
            self._parse_item(e)

        return d

    def _parse_rm(self):
        """rm (로만체) - 이탤릭 해제"""
        container = ET.Element(_m('oMath'))
        # rm 이후의 요소를 일반 텍스트로
        elem = self._parse_primary()
        if elem is not None:
            # 로만체 속성 적용
            self._set_roman(elem)
            container.append(elem)
        return container

    def _set_roman(self, elem):
        """요소에 로만체(nor) 속성 적용"""
        for r in elem.iter(_m('r')):
            rPr = r.find(_m('rPr'))
            if rPr is None:
                rPr = ET.SubElement(r, _m('rPr'))
                # insert at beginning
                r.remove(rPr)
                r.insert(0, rPr)
            nor = ET.SubElement(rPr, _m('nor'))
            nor.set(_m('val'), '1')

    def _make_run(self, text):
        """텍스트 run 요소 생성"""
        r = ET.Element(_m('r'))
        t = ET.SubElement(r, _m('t'))
        t.text = text
        return r


def hwp_eq_to_omml(script):
    """한컴 수식 스크립트를 OMML XML 요소로 변환

    Args:
        script: 한컴 수식 스크립트 문자열

    Returns:
        xml.etree.ElementTree.Element: OMML oMath 요소
    """
    if not script or not script.strip():
        omath = ET.Element(_m('oMath'))
        return omath

    try:
        tokenizer = HwpEqTokenizer(script.strip())
        tokens = tokenizer.tokenize()
        parser = HwpEqParser(tokens)
        return parser.parse()
    except Exception:
        # 파싱 실패 시 원본 스크립트를 텍스트로
        omath = ET.Element(_m('oMath'))
        r = ET.SubElement(omath, _m('r'))
        t = ET.SubElement(r, _m('t'))
        t.text = script.strip()
        return omath


def omml_to_string(omath):
    """OMML 요소를 XML 문자열로 변환 (디버그용)"""
    ET.register_namespace('m', M_NS)
    ET.register_namespace('w', W_NS)
    return ET.tostring(omath, encoding='unicode')
