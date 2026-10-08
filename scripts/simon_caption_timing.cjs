'use strict';
// The workbench supplies cues measured from speech words. Keep the vendored
// renderer unchanged, but do not let its proportional long-sentence splitter
// replace those times in the burned-in video captions.
const path = require('path');
const captions = require(path.join(__dirname, '../apps/simon-skills/skills/whiteboard-video/lib/captions.cjs'));
const original = captions.cuesForScene;
captions.cuesForScene = function (info) {
  if (!Array.isArray(info.studioCaptionCues)) return original(info);
  return info.studioCaptionCues;
};
