/**
 * 图形算式求值（`draw_figure` 的坐标、曲线、观察值）。
 *
 * 只认白名单语法：数字、参数名、点坐标（`C.x` / `C.y`）、`pi`、`+ - * / ^`、
 * 括号，以及 sqrt/abs/sin/cos/tan/min/max。**不使用 eval / new Function**，
 * 模型给的文字只被当作语法解析，越界直接报错。
 */

export type Scope = Record<string, number | { x: number; y: number }>;

export class FigureExprError extends Error {}

type Node =
  | { kind: 'number'; value: number }
  | { kind: 'name'; name: string; member: string | null }
  | { kind: 'unary'; op: '-' | '+'; operand: Node }
  | { kind: 'binary'; op: '+' | '-' | '*' | '/' | '^'; left: Node; right: Node }
  | { kind: 'call'; name: string; args: Node[] };

const FUNCTIONS = new Set(['sqrt', 'abs', 'sin', 'cos', 'tan', 'min', 'max']);
const CONSTANTS: Record<string, number> = { pi: Math.PI };

interface Token {
  type: 'number' | 'name' | 'op' | 'lparen' | 'rparen' | 'comma' | 'dot';
  text: string;
  pos: number;
}

function tokenize(input: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < input.length) {
    const ch = input[i] ?? '';
    if (/\s/.test(ch)) {
      i += 1;
      continue;
    }
    if (/[0-9]/.test(ch) || (ch === '.' && /[0-9]/.test(input[i + 1] ?? ''))) {
      const start = i;
      while (i < input.length && /[0-9.]/.test(input[i] ?? '')) i += 1;
      tokens.push({ type: 'number', text: input.slice(start, i), pos: start });
      continue;
    }
    if (/[A-Za-z_]/.test(ch)) {
      const start = i;
      while (i < input.length && /[A-Za-z0-9_]/.test(input[i] ?? '')) i += 1;
      tokens.push({ type: 'name', text: input.slice(start, i), pos: start });
      continue;
    }
    if ('+-*/^'.includes(ch)) {
      tokens.push({ type: 'op', text: ch, pos: i });
      i += 1;
      continue;
    }
    if (ch === '(') tokens.push({ type: 'lparen', text: ch, pos: i });
    else if (ch === ')') tokens.push({ type: 'rparen', text: ch, pos: i });
    else if (ch === ',') tokens.push({ type: 'comma', text: ch, pos: i });
    else if (ch === '.') tokens.push({ type: 'dot', text: ch, pos: i });
    else throw new FigureExprError(`算式里有不认识的字符「${ch}」`);
    i += 1;
  }
  return tokens;
}

class Parser {
  private index = 0;

  constructor(private readonly tokens: Token[]) {}

  parse(): Node {
    const node = this.expression();
    if (this.index < this.tokens.length) {
      const token = this.tokens[this.index];
      throw new FigureExprError(
        token === undefined ? '算式没有写完' : `算式在第 ${token.pos + 1} 个字符处多出了「${token.text}」`,
      );
    }
    return node;
  }

  private peek(): Token | undefined {
    return this.tokens[this.index];
  }

  private eat(type: Token['type'], text?: string): Token | undefined {
    const token = this.peek();
    if (token && token.type === type && (text === undefined || token.text === text)) {
      this.index += 1;
      return token;
    }
    return undefined;
  }

  private expression(): Node {
    let left = this.term();
    for (;;) {
      const token = this.peek();
      if (token?.type === 'op' && (token.text === '+' || token.text === '-')) {
        this.index += 1;
        left = { kind: 'binary', op: token.text, left, right: this.term() };
      } else {
        return left;
      }
    }
  }

  private term(): Node {
    let left = this.unary();
    for (;;) {
      const token = this.peek();
      if (token?.type === 'op' && (token.text === '*' || token.text === '/')) {
        this.index += 1;
        left = { kind: 'binary', op: token.text, left, right: this.unary() };
      } else {
        return left;
      }
    }
  }

  private unary(): Node {
    const token = this.peek();
    if (token?.type === 'op' && (token.text === '-' || token.text === '+')) {
      this.index += 1;
      return { kind: 'unary', op: token.text, operand: this.unary() };
    }
    return this.power();
  }

  private power(): Node {
    const base = this.primary();
    const token = this.peek();
    if (token?.type === 'op' && token.text === '^') {
      this.index += 1;
      // 右结合：a^b^c = a^(b^c)
      return { kind: 'binary', op: '^', left: base, right: this.unary() };
    }
    return base;
  }

  private primary(): Node {
    const token = this.peek();
    if (token === undefined) {
      throw new FigureExprError('算式没有写完');
    }
    if (token.type === 'number') {
      this.index += 1;
      const value = Number(token.text);
      if (!Number.isFinite(value)) {
        throw new FigureExprError(`数字「${token.text}」无法识别`);
      }
      return { kind: 'number', value };
    }
    if (token.type === 'lparen') {
      this.index += 1;
      const node = this.expression();
      if (this.eat('rparen') === undefined) {
        throw new FigureExprError('算式缺少右括号');
      }
      return node;
    }
    if (token.type === 'name') {
      this.index += 1;
      if (FUNCTIONS.has(token.text)) {
        if (this.eat('lparen') === undefined) {
          throw new FigureExprError(`函数 ${token.text} 后面要跟括号`);
        }
        const args: Node[] = [this.expression()];
        while (this.eat('comma') !== undefined) {
          args.push(this.expression());
        }
        if (this.eat('rparen') === undefined) {
          throw new FigureExprError(`函数 ${token.text} 缺少右括号`);
        }
        if (args.length > 2) {
          throw new FigureExprError(`函数 ${token.text} 的参数太多`);
        }
        return { kind: 'call', name: token.text, args };
      }
      let member: string | null = null;
      if (this.eat('dot') !== undefined) {
        const name = this.eat('name');
        if (name === undefined) {
          throw new FigureExprError(`「${token.text}.」后面缺少 x 或 y`);
        }
        member = name.text;
      }
      return { kind: 'name', name: token.text, member };
    }
    throw new FigureExprError(`算式里有无法解析的内容「${token.text}」`);
  }
}

function evaluate(node: Node, scope: Scope): number {
  switch (node.kind) {
    case 'number':
      return node.value;
    case 'name': {
      if (node.member === null) {
        if (node.name in CONSTANTS) return CONSTANTS[node.name] ?? NaN;
        const value = scope[node.name];
        if (typeof value === 'number') return value;
        throw new FigureExprError(`${node.name} 没有数值`);
      }
      const target = scope[node.name];
      if (target === undefined || typeof target === 'number') {
        throw new FigureExprError(`${node.name} 不是点，不能取 .${node.member}`);
      }
      if (node.member !== 'x' && node.member !== 'y') {
        throw new FigureExprError(`点坐标只能取 .x 或 .y，不能取 .${node.member}`);
      }
      return target[node.member];
    }
    case 'unary': {
      const value = evaluate(node.operand, scope);
      return node.op === '-' ? -value : value;
    }
    case 'binary': {
      const left = evaluate(node.left, scope);
      const right = evaluate(node.right, scope);
      switch (node.op) {
        case '+': return left + right;
        case '-': return left - right;
        case '*': return left * right;
        case '/': return right === 0 ? NaN : left / right;
        case '^': return left ** right;
        default: return NaN;
      }
    }
    case 'call': {
      const args = node.args.map((arg) => evaluate(arg, scope));
      const first = args[0];
      if (first === undefined) return NaN;
      switch (node.name) {
        case 'sqrt': return first < 0 ? NaN : Math.sqrt(first);
        case 'abs': return Math.abs(first);
        case 'sin': return Math.sin(first);
        case 'cos': return Math.cos(first);
        case 'tan': return Math.tan(first);
        case 'min': return Math.min(first, args[1] ?? first);
        case 'max': return Math.max(first, args[1] ?? first);
        default: return NaN;
      }
    }
    default:
      return NaN;
  }
}

export interface CompiledExpression {
  /** 当前作用域下的值；无法计算时返回 NaN。 */
  evaluate(scope: Scope): number;
  /** 引用到的名称（用于检查依赖顺序）。 */
  names: Set<string>;
}

const cache = new Map<string, CompiledExpression>();

/** 编译一个算式。语法错误抛 `FigureExprError`；未知名称在求值时报错。 */
export function compileExpression(source: string): CompiledExpression {
  const cached = cache.get(source);
  if (cached !== undefined) {
    return cached;
  }
  const node = new Parser(tokenize(source)).parse();
  const names = new Set<string>();
  const collect = (current: Node): void => {
    if (current.kind === 'name') names.add(current.name);
    else if (current.kind === 'unary') collect(current.operand);
    else if (current.kind === 'binary') {
      collect(current.left);
      collect(current.right);
    } else if (current.kind === 'call') current.args.forEach(collect);
  };
  collect(node);
  const compiled: CompiledExpression = {
    evaluate(scope: Scope): number {
      try {
        const value = evaluate(node, scope);
        return Number.isFinite(value) ? value : NaN;
      } catch {
        return NaN;
      }
    },
    names,
  };
  cache.set(source, compiled);
  return compiled;
}

/** 安全求值：任何问题都返回 NaN，不抛异常。 */
export function evaluateExpression(source: string, scope: Scope): number {
  try {
    return compileExpression(source).evaluate(scope);
  } catch {
    return NaN;
  }
}

/** 数值显示：最多 3 位小数，去掉多余的 0。 */
export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) {
    return '—';
  }
  const rounded = Math.round(value * 1000) / 1000;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(3).replace(/0+$/, '');
}

/** 用连分数找一个小分母的近似分数，找得到就显示成分数。 */
export function formatFraction(value: number, maxDenominator = 60): string {
  if (!Number.isFinite(value)) {
    return '—';
  }
  for (let denominator = 1; denominator <= maxDenominator; denominator += 1) {
    const numerator = Math.round(value * denominator);
    if (Math.abs(value - numerator / denominator) < 1e-6) {
      if (denominator === 1) {
        return String(numerator);
      }
      return `${numerator}/${denominator}`;
    }
  }
  return formatNumber(value);
}
