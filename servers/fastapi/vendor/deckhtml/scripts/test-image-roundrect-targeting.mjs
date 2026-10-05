import assert from 'node:assert/strict';
import { applyImageRoundRectToXml } from '../dist/enhancer/image-roundrect-xml.js';

const picture = (id) =>
  `<p:pic><p:nvPicPr><p:cNvPr id="${id}"/></p:nvPicPr>` +
  '<p:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>';

const source = `<p:sld>${picture('page-background')}${picture('rounded-card')}</p:sld>`;
const result = applyImageRoundRectToXml(source, {
  type: 'imageRoundRect',
  slideIndex: 0,
  elementIndex: 1,
  picIndex: 1,
  imageBorderRadiusPx: 24,
  imageWidthInch: 2,
  imageHeightInch: 1,
});

assert.match(
  result,
  /id="page-background"[\s\S]*?prstGeom prst="rect"/,
  'the page-background picture must stay rectangular',
);
assert.match(
  result,
  /id="rounded-card"[\s\S]*?prstGeom prst="roundRect"/,
  'the registered rounded image must receive the roundRect geometry',
);
assert.equal((result.match(/prst="roundRect"/g) ?? []).length, 1);

console.log('PASS image roundRect targets the registered picture only');
