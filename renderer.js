/* global cv, UTIF, exifr */
const $ = (id) => document.getElementById(id);
const originalCanvas = $('original-canvas');
const enhancedCanvas = $('enhanced-canvas');
const compareOriginal = $('compare-original');
const compareEnhanced = $('compare-enhanced');
let originalReady = false;
let fileInfo = null;
let processingTimer = null;

function cvReady() {
  return new Promise((resolve) => {
    const check = () => {
      if (window.cv && cv.Mat && cv.imread) resolve();
      else setTimeout(check, 30);
    };
    check();
  });
}

function setBusy(value) { $('busy').hidden = !value; }
function currentSettings() {
  return { clip: Number($('clip-limit').value), tile: Number($('tile-size').value), diameter: Number($('diameter').value), sigmaColor: Number($('sigma-color').value), sigmaSpace: Number($('sigma-space').value) };
}
function updateOutputs() {
  for (const input of document.querySelectorAll('input[type=range]')) $(`${input.id}-output`).value = input.value;
}
function canvasContext(canvas) { return canvas.getContext('2d', { willReadFrequently: true }); }

async function decodeImage(bytes, extension) {
  const isTiff = ['TIF', 'TIFF'].includes(extension);
  if (isTiff) {
    const frames = UTIF.decode(bytes);
    if (!frames.length) throw new Error('No TIFF frame could be decoded.');
    UTIF.decodeImage(bytes, frames[0]);
    const rgba = UTIF.toRGBA8(frames[0]);
    const canvas = document.createElement('canvas');
    canvas.width = frames[0].width; canvas.height = frames[0].height;
    canvasContext(canvas).putImageData(new ImageData(new Uint8ClampedArray(rgba), canvas.width, canvas.height), 0, 0);
    return canvas;
  }
  const blob = new Blob([bytes]);
  const bitmap = await createImageBitmap(blob, { imageOrientation: 'from-image' });
  const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height;
  canvasContext(canvas).drawImage(bitmap, 0, 0); bitmap.close(); return canvas;
}

function drawFullResolution(target, source) {
  target.width = source.width; target.height = source.height;
  canvasContext(target).drawImage(source, 0, 0);
}
function renderMetadata(width, height, extension, exif) {
  const format = extension === 'JPG' ? 'JPEG' : extension;
  const orientation = exif?.Orientation ? `<div><b>EXIF orientation</b> ${exif.Orientation}</div>` : '';
  $('metadata').classList.remove('empty');
  $('metadata').innerHTML = `<div><b>Dimensions</b> ${width.toLocaleString()} × ${height.toLocaleString()}</div><div><b>Channels</b> RGBA (source preserved)</div><div><b>Format</b> ${format}</div>${orientation}`;
}

function enhance() {
  if (!originalReady || !window.cv || !cv.imread) return;
  setBusy(true);
  requestAnimationFrame(() => {
    let source, rgb, lab, l, a, b, merged, equalizedL, clahe, equalizedLab, enhancedRgb, alpha, enhancedRgba;
    try {
      const s = currentSettings();
      source = cv.imread(originalCanvas); // Exact original pixel dimensions; no crop or scale.
      rgb = new cv.Mat(); cv.cvtColor(source, rgb, cv.COLOR_RGBA2RGB);
      lab = new cv.Mat(); cv.cvtColor(rgb, lab, cv.COLOR_RGB2Lab);
      const labChannels = new cv.MatVector(); cv.split(lab, labChannels);
      l = labChannels.get(0); a = labChannels.get(1); b = labChannels.get(2); labChannels.delete();
      clahe = cv.createCLAHE(s.clip, new cv.Size(s.tile, s.tile));
      equalizedL = new cv.Mat(); clahe.apply(l, equalizedL); clahe.delete();
      merged = new cv.MatVector(); merged.push_back(equalizedL); merged.push_back(a); merged.push_back(b);
      equalizedLab = new cv.Mat(); cv.merge(merged, equalizedLab); merged.delete();
      enhancedRgb = new cv.Mat(); cv.cvtColor(equalizedLab, enhancedRgb, cv.COLOR_Lab2RGB);
      const filtered = new cv.Mat(); cv.bilateralFilter(enhancedRgb, filtered, s.diameter, s.sigmaColor, s.sigmaSpace); enhancedRgb.delete();
      alpha = new cv.Mat(); cv.extractChannel(source, alpha, 3);
      enhancedRgba = new cv.Mat(); cv.cvtColor(filtered, enhancedRgba, cv.COLOR_RGB2RGBA); filtered.delete(); cv.insertChannel(alpha, enhancedRgba, 3);
      cv.imshow(enhancedCanvas, enhancedRgba);
      drawFullResolution(compareOriginal, originalCanvas); drawFullResolution(compareEnhanced, enhancedCanvas);
      $('enhanced-size').textContent = `${originalCanvas.width.toLocaleString()} × ${originalCanvas.height.toLocaleString()} px`;
      $('save-button').disabled = false;
    } catch (error) { console.error(error); alert(`Could not enhance image: ${error.message}`); }
    finally { [source, rgb, lab, l, a, b, equalizedL, equalizedLab, alpha, enhancedRgba].forEach((mat) => mat?.delete?.()); setBusy(false); }
  });
}
function queueEnhance() { clearTimeout(processingTimer); processingTimer = setTimeout(enhance, 70); }

async function openImage() {
  if (!window.cv || !cv.imread) return;
  const selected = await window.desktopAPI.openImage(); if (!selected) return;
  try {
    setBusy(true); $('save-button').disabled = true;
    const bytes = selected.data;
    const decoded = await decodeImage(bytes, selected.extension);
    drawFullResolution(originalCanvas, decoded); drawFullResolution(compareOriginal, decoded);
    fileInfo = selected; originalReady = true;
    $('original-size').textContent = `${decoded.width.toLocaleString()} × ${decoded.height.toLocaleString()} px`;
    let exif = null; try { exif = await exifr.parse(bytes, { translateValues: false }); } catch (_) { /* EXIF is optional. */ }
    renderMetadata(decoded.width, decoded.height, selected.extension, exif); enhance();
  } catch (error) { setBusy(false); alert(`Could not open image: ${error.message}`); }
}
async function saveEnhanced() {
  if (!originalReady) return;
  const blob = await new Promise((resolve) => enhancedCanvas.toBlob(resolve, 'image/png'));
  if (!blob) return alert('Unable to encode the enhanced PNG.');
  const baseName = fileInfo.name.replace(/\.[^.]+$/, '');
  const saved = await window.desktopAPI.saveEnhancedPng({ data: await blob.arrayBuffer(), suggestedName: `${baseName}_enhanced.png` });
  if (saved) $('save-button').textContent = 'Saved Enhanced Image';
}
function selectTab(tab) {
  for (const button of document.querySelectorAll('[data-tab]')) button.classList.toggle('active', button.dataset.tab === tab);
  $('original-view').hidden = tab !== 'original'; $('enhanced-view').hidden = tab !== 'enhanced'; $('compare-view').hidden = tab !== 'compare';
}

window.addEventListener('DOMContentLoaded', async () => {
  updateOutputs();
  for (const input of document.querySelectorAll('input[type=range]')) input.addEventListener('input', () => { updateOutputs(); queueEnhance(); });
  $('open-button').addEventListener('click', openImage); $('save-button').addEventListener('click', saveEnhanced);
  document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', () => selectTab(button.dataset.tab)));
  await cvReady(); $('engine-status').textContent = 'OpenCV engine ready'; $('engine-status').classList.replace('loading', 'ready');
});
