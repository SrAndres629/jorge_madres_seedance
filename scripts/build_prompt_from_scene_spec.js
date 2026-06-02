const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');

const BASE = process.env.PROJECT_ROOT || process.cwd();
const SPECS_PATH = path.join(BASE, "00_config/scene_specs.final_7_native_audio.json");
const PROMPTS_DIR = path.join(BASE, "02_prompts/compiled");
const PAYLOADS_DIR = path.join(BASE, "04_logs/dry_run_payloads");
const VALIDATION_DIR = path.join(BASE, "04_logs/validation");
const CONFIG_PATH = path.join(BASE, "00_config/campaign_config.json");

[PROMPTS_DIR, PAYLOADS_DIR, VALIDATION_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

const jsonValidationReport = {
  campaignConfig: { parsed: false, error: null },
  sceneSpecs: { parsed: false, error: null, isArray: false, length: 0, expectedLength: 7 },
  overall: false
};

let config, specs;

try {
  const rawConfig = fs.readFileSync(CONFIG_PATH, 'utf8');
  config = JSON.parse(rawConfig);
  jsonValidationReport.campaignConfig.parsed = true;
} catch (e) {
  jsonValidationReport.campaignConfig.error = e.message;
}

try {
  const rawSpecs = fs.readFileSync(SPECS_PATH, 'utf8');
  specs = JSON.parse(rawSpecs);
  jsonValidationReport.sceneSpecs.parsed = true;
  jsonValidationReport.sceneSpecs.isArray = Array.isArray(specs);
  jsonValidationReport.sceneSpecs.length = Array.isArray(specs) ? specs.length : 0;
} catch (e) {
  jsonValidationReport.sceneSpecs.error = e.message;
}

jsonValidationReport.overall =
  jsonValidationReport.campaignConfig.parsed &&
  jsonValidationReport.sceneSpecs.parsed &&
  jsonValidationReport.sceneSpecs.isArray &&
  jsonValidationReport.sceneSpecs.length === 7;

if (!jsonValidationReport.overall) {
  fs.writeFileSync(
    path.join(VALIDATION_DIR, "json_validation_report.json"),
    JSON.stringify(jsonValidationReport, null, 2),
    'utf8'
  );
  console.error("JSON VALIDATION FAILED. See 04_logs/validation/json_validation_report.json");
  process.exit(1);
}

fs.writeFileSync(
  path.join(VALIDATION_DIR, "json_validation_report.json"),
  JSON.stringify(jsonValidationReport, null, 2),
  'utf8'
);

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

function compileNativeAudio(audio) {
  const parts = [];
  const musicText = audio.music.includes("from the first second")
    ? audio.music
    : audio.music + " from the first second";
  parts.push("Generate native synchronized audio with " + musicText + ".");
  parts.push("Add sound effects: " + audio.sfx + ".");
  parts.push("Use an " + audio.voiceType + " saying only: \"" + audio.voiceLine + "\".");
  if (audio.lipSync) {
    parts.push("Lip sync is required.");
  } else {
    parts.push("The voice is narration, not lip-sync. Jorge does not sing or speak on camera.");
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
  lines.push(compileNativeAudio(scene.nativeAudio));
  lines.push("");
  lines.push("Constraints:");
  for (const c of scene.constraints) {
    lines.push("- " + c);
  }
  return lines.join("\n");
}

const fieldValidationReport = {
  totalScenes: specs.length,
  scenesWithErrors: 0,
  errors: [],
  ok: true
};

const requiredTopFields = [
  "sceneId", "duration", "references", "subject", "action",
  "environment", "camera", "style", "nativeAudio", "constraints",
  "outputName", "approvalCriteria"
];

const requiredCameraFields = ["format", "movement", "lens", "speed", "focus_order"];
const requiredAudioFields = ["music", "sfx", "voiceType", "voiceLine", "lipSync"];

for (const scene of specs) {
  const sceneErrors = [];

  for (const field of requiredTopFields) {
    if (scene[field] === undefined || scene[field] === null) {
      sceneErrors.push(`Missing required field: ${field}`);
    }
  }

  if (scene.camera) {
    for (const field of requiredCameraFields) {
      if (scene.camera[field] === undefined || scene.camera[field] === null) {
        sceneErrors.push(`Missing camera.${field}`);
      }
    }
  }

  if (scene.nativeAudio) {
    for (const field of requiredAudioFields) {
      if (scene.nativeAudio[field] === undefined || scene.nativeAudio[field] === null) {
        sceneErrors.push(`Missing nativeAudio.${field}`);
      }
    }
  }

  if (sceneErrors.length > 0) {
    fieldValidationReport.errors.push({ sceneId: scene.sceneId || "unknown", errors: sceneErrors });
    fieldValidationReport.scenesWithErrors++;
    fieldValidationReport.ok = false;
  }
}

// Always write field validation report
fs.writeFileSync(
  path.join(VALIDATION_DIR, "field_validation_report.json"),
  JSON.stringify(fieldValidationReport, null, 2),
  'utf8'
);

if (!fieldValidationReport.ok) {
  console.error("FIELD VALIDATION FAILED. See 04_logs/validation/field_validation_report.json");
  process.exit(1);
}

function checkUrl(url, timeoutMs = 10000) {
  return new Promise((resolve) => {
    try {
      const lib = url.startsWith('https') ? https : http;
      const req = lib.get(url, { timeout: timeoutMs }, (res) => {
        resolve({ url, statusCode: res.statusCode, ok: res.statusCode === 200 });
      });
      req.on('error', (err) => {
        resolve({ url, statusCode: 0, ok: false, error: err.message });
      });
      req.on('timeout', () => {
        req.destroy();
        resolve({ url, statusCode: 0, ok: false, error: 'timeout' });
      });
    } catch (err) {
      resolve({ url, statusCode: 0, ok: false, error: err.message });
    }
  });
}

async function main() {
  const compileReport = {
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

  const urlValidationResults = [];
  let publicUrlsReady = true;

  for (const scene of specs) {
    const prompt = compilePrompt(scene);
    const promptPath = path.join(PROMPTS_DIR, `prompt_${scene.sceneId}.txt`);
    fs.writeFileSync(promptPath, prompt, 'utf8');
    compileReport.compiledPrompts++;
    compileReport.promptPaths.push(`02_prompts/compiled/prompt_${scene.sceneId}.txt`);

    const referenceUrls = scene.references.map(ref => BASE_URL + ref);

    const urlChecks = await Promise.all(referenceUrls.map(url => checkUrl(url)));
    for (const check of urlChecks) {
      urlValidationResults.push({ sceneId: scene.sceneId, ...check });
      if (!check.ok) {
        publicUrlsReady = false;
      }
    }

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

    const expectedDuration = (scene.sceneId.startsWith("06") || scene.sceneId.startsWith("07")) ? 5 : 4;
    if (payload.input.duration !== expectedDuration) {
      payloadReport.validations.correctDurations = false;
      payloadReport.errors.push({
        sceneId: scene.sceneId,
        expected: expectedDuration,
        actual: payload.input.duration
      });
    }

    for (const url of referenceUrls) {
      if (!url.startsWith("https://raw.githubusercontent.com/")) {
        payloadReport.validations.urlsUseRawGithub = false;
      }
    }
  }

  const urlValidationReport = {
    publicUrlsReady: publicUrlsReady,
    totalUrlsChecked: urlValidationResults.length,
    results: urlValidationResults
  };

  fs.writeFileSync(
    path.join(VALIDATION_DIR, "public_url_validation_report.json"),
    JSON.stringify(urlValidationReport, null, 2),
    'utf8'
  );

  fs.writeFileSync(
    path.join(VALIDATION_DIR, "prompt_compile_report.json"),
    JSON.stringify(compileReport, null, 2),
    'utf8'
  );

  fs.writeFileSync(
    path.join(VALIDATION_DIR, "dry_run_payload_report.json"),
    JSON.stringify(payloadReport, null, 2),
    'utf8'
  );

  console.log(JSON.stringify({
    jsonValidation: "passed",
    fieldValidation: fieldValidationReport.ok ? "passed" : "failed",
    promptsCompiled: compileReport.compiledPrompts,
    payloadsGenerated: payloadReport.totalPayloads,
    urlsChecked: urlValidationResults.length,
    publicUrlsReady: publicUrlsReady,
    promptOk: compileReport.ok,
    payloadValidations: payloadReport.validations,
    reports: {
      json: "04_logs/validation/json_validation_report.json",
      fields: "04_logs/validation/field_validation_report.json",
      urls: "04_logs/validation/public_url_validation_report.json",
      prompts: "04_logs/validation/prompt_compile_report.json",
      payloads: "04_logs/validation/dry_run_payload_report.json"
    }
  }, null, 2));
}

main().catch(err => {
  console.error("Fatal error:", err.message);
  process.exit(1);
});
