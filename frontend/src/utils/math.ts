/**
 * 把模型可能使用的 LaTeX 定界符统一成 remark-math 认识的 `$` / `$$`。
 *
 * - `\[ ... \]` → 独立公式 `$$ ... $$`
 * - `\( ... \)` → 行内公式 `$ ... $`
 *
 * 代码块和行内代码中的内容保持原样。
 */
export function normalizeMathDelimiters(markdown: string): string {
  // 按代码片段切分：奇数段是代码，不处理。
  const parts = markdown.split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  return parts
    .map((part, index) => {
      if (index % 2 === 1) {
        return part;
      }
      return part
        .replace(/\\\[([\s\S]+?)\\\]/g, (_, body: string) => `\n$$\n${body.trim()}\n$$\n`)
        .replace(/\\\(([\s\S]+?)\\\)/g, (_, body: string) => `$${body.trim()}$`);
    })
    .join('');
}
