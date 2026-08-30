/** 复制文本：优先 Clipboard API，失败退回 execCommand（兼容 http 非安全上下文）。 */

export async function copyText(text: string): Promise<boolean> {
  // 直接尝试 Clipboard API（不依赖 isSecureContext 判断，部分浏览器在
  // localhost / 非严格上下文仍允许 writeText）
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // 继续走 execCommand 兜底
  }
  return execCommandCopy(text);
}

function execCommandCopy(text: string): boolean {
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    // 离屏而非透明：部分浏览器对 opacity:0 元素不执行复制
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    ta.style.top = '0';
    document.body.appendChild(ta);
    const selection = document.getSelection();
    const prevRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, text.length);
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch {
      ok = false;
    }
    document.body.removeChild(ta);
    if (prevRange && selection) {
      selection.removeAllRanges();
      selection.addRange(prevRange);
    }
    return ok;
  } catch {
    return false;
  }
}
