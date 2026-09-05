// Read-only browser diagnostic. Run against the reopened draft's article root.
// This code belongs to the host's test session, NEVER the article HTML/SVG.
function measureWechatViewport(root) {
  if (!root) throw new Error("Select the exact saved-draft article root");
  const rect = root.getBoundingClientRect();
  return {
    width_px: Math.round(rect.width),
    captured_at: new Date().toISOString(),
    text_layers: Array.from(root.querySelectorAll("[data-transport-text-node-id]")).map(node => {
      const style = getComputedStyle(node), box = node.getBoundingClientRect();
      return {
        node_id: node.getAttribute("data-transport-text-node-id"),
        font_size_px: parseFloat(style.fontSize),
        letter_spacing_px: style.letterSpacing === "normal" ? 0 : parseFloat(style.letterSpacing),
        width_px: box.width, height_px: box.height,
        scroll_height_px: node.scrollHeight, scroll_width_px: node.scrollWidth
      };
    })
  };
}
if (typeof module !== "undefined") module.exports = measureWechatViewport;
