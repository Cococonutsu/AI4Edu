import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { normalizeMathDelimiters } from '../utils/math';

const components: Components = {
  a({ href, children, title }) {
    return (
      <a href={href} title={title} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
  img({ src, alt, title }) {
    return <img src={src} alt={alt ?? ''} title={title} className="markdown-image" loading="lazy" />;
  },
};

export function MarkdownContent({ children }: { children: string }): JSX.Element {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}
        components={components}
        // 不启用 rehype-raw：模型返回的原始 HTML 一律按文本处理。
      >
        {normalizeMathDelimiters(children)}
      </ReactMarkdown>
    </div>
  );
}
