// @ts-check
/* Building the page: elements made in code (no HTML strings, so no injection). */

/**
 * A new element: `attrs` become properties, attributes, or listeners (`on…`).
 * @template {keyof HTMLElementTagNameMap} K
 * @param {K} tag
 * @param {Object<string, any>} [attrs]
 * @param {...any} children nodes, text, or (nested) lists of them
 * @returns {HTMLElementTagNameMap[K]}
 */
export function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key in node && key !== 'list') node[key] = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
