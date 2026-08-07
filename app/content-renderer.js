(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ContentRenderer = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function inlineMarkdown(value) {
    return escapeHtml(value)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  }

  function renderSequenceDiagram(source) {
    const participants = [];
    const steps = [];
    for (const line of source.split(/\r?\n/)) {
      const participant = line.match(/^\s*participant\s+(.+?)\s*$/);
      if (participant && !participants.includes(participant[1])) participants.push(participant[1]);
      const arrow = line.match(/^\s*(.+?)(--?>>)(.+?):\s*(.+?)\s*$/);
      if (arrow) {
        const [, from, glyph, to, message] = arrow;
        if (!participants.includes(from.trim())) participants.push(from.trim());
        if (!participants.includes(to.trim())) participants.push(to.trim());
        steps.push({ from: from.trim(), to: to.trim(), message, reply: glyph.startsWith('--') });
      }
    }
    if (!steps.length) {
      return `<pre><code data-language="mermaid">${escapeHtml(source)}</code></pre>`;
    }
    const actors = participants.map(name => `<span class="sequence-actor">${escapeHtml(name)}</span>`).join('');
    const renderedSteps = steps.map((step, index) => `
      <li class="sequence-step${step.reply ? ' reply' : ''}">
        <span class="sequence-number">${index + 1}</span>
        <span class="sequence-from">${escapeHtml(step.from)}</span>
        <span class="sequence-arrow" aria-hidden="true">${step.reply ? '⇠' : '→'}</span>
        <span class="sequence-to">${escapeHtml(step.to)}</span>
        <span class="sequence-message">${escapeHtml(step.message)}</span>
      </li>`).join('');
    return `<figure class="sequence-diagram"><figcaption>Sequence diagram</figcaption><div class="sequence-actors">${actors}</div><ol>${renderedSteps}</ol></figure>`;
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown ?? '').split(/\r?\n/);
    const output = [];
    let paragraph = [];
    let code = null;
    let language = '';

    function flushParagraph() {
      if (paragraph.length) output.push(`<p>${inlineMarkdown(paragraph.join(' '))}</p>`);
      paragraph = [];
    }

    for (const line of lines) {
      const fence = line.match(/^```\s*([A-Za-z0-9_-]*)\s*$/);
      if (fence) {
        flushParagraph();
        if (code === null) {
          code = [];
          language = fence[1].toLowerCase();
        } else {
          const source = code.join('\n');
          output.push(language === 'mermaid'
            ? renderSequenceDiagram(source)
            : `<pre><code data-language="${escapeHtml(language)}">${escapeHtml(source)}</code></pre>`);
          code = null;
          language = '';
        }
        continue;
      }
      if (code !== null) {
        code.push(line);
        continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        const level = heading[1].length;
        output.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      } else if (/^\s*[-*]\s+/.test(line)) {
        flushParagraph();
        const item = line.replace(/^\s*[-*]\s+/, '');
        const previous = output.at(-1) || '';
        if (previous.startsWith('<ul>')) {
          output[output.length - 1] = previous.replace('</ul>', `<li>${inlineMarkdown(item)}</li></ul>`);
        } else {
          output.push(`<ul><li>${inlineMarkdown(item)}</li></ul>`);
        }
      } else if (!line.trim()) {
        flushParagraph();
      } else {
        paragraph.push(line.trim());
      }
    }
    if (code !== null) {
      output.push(`<pre><code data-language="${escapeHtml(language)}">${escapeHtml(code.join('\n'))}</code></pre>`);
    }
    flushParagraph();
    return output.join('\n');
  }

  function renderOpenApi(yaml) {
    const lines = String(yaml ?? '').split(/\r?\n/);
    let title = 'OpenAPI specification';
    let version = '';
    let inInfo = false;
    let inPaths = false;
    let currentPath = null;
    let currentOperation = null;
    const operations = [];

    for (const line of lines) {
      if (line === 'info:') { inInfo = true; inPaths = false; continue; }
      if (line === 'paths:') { inPaths = true; inInfo = false; continue; }
      if (/^[A-Za-z]/.test(line) && !line.startsWith('paths:') && !line.startsWith('info:')) {
        inInfo = false;
        if (!line.startsWith('openapi:')) inPaths = false;
      }
      if (inInfo) {
        const titleMatch = line.match(/^\s{2}title:\s*(.+?)\s*$/);
        const versionMatch = line.match(/^\s{2}version:\s*(.+?)\s*$/);
        if (titleMatch) title = titleMatch[1].replace(/^['"]|['"]$/g, '');
        if (versionMatch) version = versionMatch[1].replace(/^['"]|['"]$/g, '');
      }
      if (!inPaths) continue;
      const pathMatch = line.match(/^\s{2}(\/[^:]+(?:\{[^}]+\}[^:]*)?):\s*$/);
      if (pathMatch) { currentPath = pathMatch[1]; currentOperation = null; continue; }
      const methodMatch = line.match(/^\s{4}(get|post|put|patch|delete|head|options):\s*$/i);
      if (methodMatch && currentPath) {
        currentOperation = { method: methodMatch[1].toUpperCase(), path: currentPath, operationId: '', summary: '' };
        operations.push(currentOperation);
        continue;
      }
      if (currentOperation) {
        const operationId = line.match(/^\s{6}operationId:\s*(.+?)\s*$/);
        const summary = line.match(/^\s{6}summary:\s*(.+?)\s*$/);
        if (operationId) currentOperation.operationId = operationId[1];
        if (summary) currentOperation.summary = summary[1];
      }
    }

    const cards = operations.map(operation => `<li class="oas-operation"><span class="oas-method ${operation.method.toLowerCase()}">${escapeHtml(operation.method)}</span><code class="oas-path">${escapeHtml(operation.path)}</code><strong>${escapeHtml(operation.summary || operation.operationId)}</strong><code>${escapeHtml(operation.operationId)}</code></li>`).join('');
    return `<section class="oas-summary"><h3>${escapeHtml(title)}</h3>${version ? `<p>Version ${escapeHtml(version)}</p>` : ''}<ul>${cards || '<li>No operations found.</li>'}</ul></section>`;
  }

  function detectContentKind(document) {
    if (document?.content_type === 'text/markdown') return 'markdown';
    if (document?.content_type === 'application/yaml' && String(document?.format || '').startsWith('openapi-')) return 'openapi';
    return null;
  }

  return { detectContentKind, escapeHtml, renderMarkdown, renderOpenApi, renderSequenceDiagram };
}));
