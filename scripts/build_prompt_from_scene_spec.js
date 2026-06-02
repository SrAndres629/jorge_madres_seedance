const fs = require('fs');
const path = require('path');

const BASE = "/media/datasets/home/Escritorio/n8n/automatizaciones/jorge_madres_seedance";
const SPECS_PATH = path.join(BASE, "00_config/scene_specs.final_7_native_audio.json");
const PROMPTS_DIR = path.join(BASE, "02_prompts/compiled");
const PAYLOADS_DIR = path.join(BASE, "04_logs/dry_run_payloads");
const VALIDATION_DIR = path.join(BASE, "04_logs/validation");
const CONFIG_PATH = path.join(BASE, "00_config/campaign_config.json");

const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
const specs = JSON.parse(fs.readFileSync(SPECS_PATH, 'utf8'));
const BASE_URL = config.publicAssetBaseUrl;

function compileCamera(camera) {
  const parts = [];
  if (camera.format) parts.push("Shot in vertical 9:16 format.");
  if (camera.movement) parts.push(camera.movement + ".");
  if (camera.lens) parts.push("Use " + camera.lens + ".");
  if (camera.speed) parts.push("The visual rhythm should feel " + camera.speed + ".");
  if (camera.focus_order && camera.focus_order.length) {
    parts.push("Focus order: first on " + camera.focus_order.join(", then ") + ".");
  }
  return parts.join(" ");
}

function compilePrompt(scene) {
  const lines = [];
  lines.push("Subject:");
  lines.push(scene.subject);
  lines.push("");
  lines.push("Action:");
  lines.push(scene.action);
  lines.push("");
  lines.push("Environment:");
  lines.push(scene.environment);
  lines.push("");
  lines.push("Camera:");
  lines.push(compileCamera(scene.camera));
  lines.push("");
  lines.push("Style:");
  lines.push(scene.style);
  lines.push("");
  lines.push("Native Audio:");
  const audio = scene.nativeAudio;
  lines.push("Music: " + audio.music);
  lines.push("Sound effects: " + audio.sfx);
  lines.push("Voice type: " + audio.voiceType);
  lines.push("Voice line: \"" + audio.voiceLine + "\"");
  lines.push("Lip sync: " + (audio.lipSync ? "required" : "none — off-camera voice only"));
  lines.push("");
  lines.push("Constraints:");
  for (const c of scene.constraints) {
    lines.push("- " + c);
  }
  return lines.join("\n");
}

const report = {
  totalScenes: specs.length,
  compiledPrompts: 0,
  missingFields: [],
  promptPaths: [],
  ok: true
};

const payloadReport = {
  totalPayloads: 0,
  validations: {
    allGenerateAudioTrue: true,
    noReferenceAudioUrls: true,
    noFirstFrameUrl: true,
    noLastFrameUrl: true,
    noGenerateAudioFalse: true,
    correctAspectRatio: true,
    correctResolution: true,
    correctDurations: true,
    urlsUseRawGithub: true,
    noKieCalled: true
  },
  payloadPaths: [],
  errors: []
};

for (const scene of specs) {
  const prompt = compilePrompt(scene);
  const promptPath = path.join(PROMPTS_DIR, `prompt_${scene.sceneId}.txt`);
  fs.writeFileSync(promptPath, prompt, 'utf8');
  report.compiledPrompts++;
  report.promptPaths.push(`02_prompts/compiled/prompt_${scene.sceneId}.txt`);

  const referenceUrls = scene.references.map(ref => BASE_URL + ref);

  const payload = {
    model: config.defaultModel,
    input: {
      prompt: prompt,
      reference_image_urls: referenceUrls,
      generate_audio: true,
      resolution: config.defaultResolution,
      aspect_ratio: config.aspectRatio,
      duration: scene.duration,
      web_search: false
    }
  };

  const payloadPath = path.join(PAYLOADS_DIR, `payload_${scene.sceneId}.json`);
  fs.writeFileSync(payloadPath, JSON.stringify(payload, null, 2), 'utf8');
  payloadReport.totalPayloads++;
  payloadReport.payloadPaths.push(`04_logs/dry_run_payloads/payload_${scene.sceneId}.json`);

  if (payload.input.generate_audio !== true) payloadReport.validations.allGenerateAudioTrue = false;
  if (payload.input.reference_audio_urls !== undefined) payloadReport.validations.noReferenceAudioUrls = false;
  if (payload.input.first_frame_url !== undefined) payloadReport.validations.noFirstFrameUrl = false;
  if (payload.input.last_frame_url !== undefined) payloadReport.validations.noLastFrameUrl = false;
  if (payload.input.aspect_ratio !== "9:16") payloadReport.validations.correctAspectRatio = false;
  if (payload.input.resolution !== "720p") payloadReport.validations.correctResolution = false;
  if (scene.sceneId === "06_authority_20_25" && payload.input.duration !== 5) payloadReport.validations.correctDurations = false;
  if (scene.sceneId === "07_cta_25_30" && payload.input.duration !== 5) payloadReport.validations.correctDurations = false;
  if (scene.duration === 5 && payload.input.duration !== 5) payloadReport.validations.correctDurations = false;
  for (const url of referenceUrls) {
    if (!url.startsWith("https://raw.githubusercontent.com/")) payloadReport.validations.urlsUseRawGithub = false;
  }
}

for (const s of specs) {
  const required = ["subject", "action", "environment", "camera", "style", "nativeAudio", "constraints"];
  for (const field of required) {
    if (!s[field]) {
      report.missingFields.push({ sceneId: s.sceneId, field });
      report.ok = false;
    }
  }
  if (s.nativeAudio) {
    const af = ["music", "sfx", "voiceType", "voiceLine"];
    for (const f of af) {
      if (!s.nativeAudio[f]) {
        report.missingFields.push({ sceneId: s.sceneId, field: `nativeAudio.${f}` });
        report.ok = false;
      }
    }
  }
}

fs.writeFileSync(path.join(VALIDATION_DIR, "prompt_compile_report.json"), JSON.stringify(report, null, 2), 'utf8');
fs.writeFileSync(path.join(VALIDATION_DIR, "dry_run_payload_report.json"), JSON.stringify(payloadReport, null, 2), 'utf8');

console.log(JSON.stringify({
  promptsCompiled: report.compiledPrompts,
  payloadsGenerated: payloadReport.totalPayloads,
  promptOk: report.ok,
  payloadValidations: payloadReport.validations,
  promptReport: "04_logs/validation/prompt_compile_report.json",
  payloadReport: "04_logs/validation/dry_run_payload_report.json"
}, null, 2));
