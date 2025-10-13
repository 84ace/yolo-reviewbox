/**
 * Generates a consistent color from a string.
 * @param {string} str The input string (e.g., class name).
 * @returns {string} An HSL color string.
 */
function colorFromString(str) {
  if (!str) return '#ff6a00'; // Default color
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash % 360);
  return `hsl(${h}, 70%, 50%)`;
}