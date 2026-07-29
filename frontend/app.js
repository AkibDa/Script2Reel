(() => {
  const form = document.getElementById("reel-form");
  const generateBtn = document.getElementById("generate-btn");
  const resetBtn = document.getElementById("reset-btn");
  const retryBtn = document.getElementById("retry-btn");
  const progressPanel = document.getElementById("progress-panel");
  const resultPanel = document.getElementById("result-panel");
  const statusText = document.getElementById("status-text");
  const errorText = document.getElementById("error-text");
  const resultVideo = document.getElementById("result-video");
  const downloadMp4 = document.getElementById("download-mp4");
  const downloadSrt = document.getElementById("download-srt");
  const agentOutputsJson = document.getElementById("agent-outputs-json");
  const duckVolume = document.getElementById("duck_volume");
  const duckVolumeValue = document.getElementById("duck_volume_value");

  let currentJobId = null;
  let pollTimer = null;

  duckVolume.addEventListener("input", () => {
    duckVolumeValue.textContent = Number(duckVolume.value).toFixed(2);
  });

  function clearPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function setBusy(busy) {
    generateBtn.disabled = busy;
    retryBtn.disabled = busy;
  }

  function showProgress(stage, progress, agentStatus) {
    progressPanel.classList.remove("hidden");
    statusText.textContent = stage || "Working...";
    
    if (agentStatus) {
      Object.entries(agentStatus).forEach(([agent, status]) => {
        const item = document.querySelector(`.agent-item[data-agent="${agent}"]`);
        if (item) {
          item.classList.remove("is-running", "is-completed", "is-failed");
          
          const label = item.querySelector(".agent-status");
          if (status === "running") {
            item.classList.add("is-running");
            if (label) label.textContent = "Running";
          } else if (status === "completed") {
            item.classList.add("is-completed");
            if (label) label.textContent = "Completed";
          } else if (status === "failed") {
            item.classList.add("is-failed");
            if (label) label.textContent = "Failed";
          } else {
            if (label) label.textContent = "Pending";
          }
        }
      });
    }
  }

  function showError(message) {
    errorText.textContent = message || "Generation failed.";
    errorText.classList.remove("hidden");
    retryBtn.classList.remove("hidden");
  }

  function hideError() {
    errorText.classList.add("hidden");
    errorText.textContent = "";
    retryBtn.classList.add("hidden");
  }

  function hideResult() {
    resultPanel.classList.add("hidden");
    resultVideo.removeAttribute("src");
    resultVideo.load();
    agentOutputsJson.textContent = "";
  }

  async function startJob() {
    hideError();
    hideResult();
    setBusy(true);
    
    const spinnerContainer = document.querySelector(".spinner-container");
    if (spinnerContainer) {
      spinnerContainer.classList.remove("is-done", "is-failed");
    }
    
    showProgress("Submitting job...", 0);

    const formData = new FormData(form);
    if (currentJobId) {
      formData.set("job_id", currentJobId);
    } else {
      formData.delete("job_id");
    }

    // Empty optional key should not be sent as blank string preference — backend handles it.
    if (!formData.get("eleven_key")) {
      formData.delete("eleven_key");
    }

    const musicInput = document.getElementById("bg_music");
    if (!musicInput.files || musicInput.files.length === 0) {
      formData.delete("bg_music");
    }

    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        body: formData,
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = data.detail;
        const message = Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
          : (detail || `Request failed (${res.status})`);
        throw new Error(message);
      }

      currentJobId = data.job_id;
      showProgress("Queued", 0);
      startPolling(currentJobId);
    } catch (err) {
      setBusy(false);
      const spinnerContainer = document.querySelector(".spinner-container");
      if (spinnerContainer) {
        spinnerContainer.classList.remove("is-done");
        spinnerContainer.classList.add("is-failed");
      }
      showError(err.message || String(err));
    }
  }

  function startPolling(jobId) {
    clearPoll();
    pollTimer = setInterval(() => pollJob(jobId), 2000);
    pollJob(jobId);
  }

  async function pollJob(jobId) {
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `Status check failed (${res.status})`);
      }

      showProgress(data.stage, data.progress, data.agent_status);

      if (data.status === "done") {
        clearPoll();
        setBusy(false);
        const spinnerContainer = document.querySelector(".spinner-container");
        if (spinnerContainer) {
          spinnerContainer.classList.remove("is-failed");
          spinnerContainer.classList.add("is-done");
        }
        await showResult(jobId);
      } else if (data.status === "failed") {
        clearPoll();
        setBusy(false);
        const spinnerContainer = document.querySelector(".spinner-container");
        if (spinnerContainer) {
          spinnerContainer.classList.remove("is-done");
          spinnerContainer.classList.add("is-failed");
        }
        showError(data.error || "Generation failed.");
      }
    } catch (err) {
      clearPoll();
      setBusy(false);
      const spinnerContainer = document.querySelector(".spinner-container");
      if (spinnerContainer) {
        spinnerContainer.classList.remove("is-done");
        spinnerContainer.classList.add("is-failed");
      }
      showError(err.message || String(err));
    }
  }

  async function showResult(jobId) {
    const videoUrl = `/api/jobs/${jobId}/video?t=${Date.now()}`;
    const srtUrl = `/api/jobs/${jobId}/subtitles`;

    resultVideo.src = videoUrl;
    downloadMp4.href = videoUrl;
    downloadSrt.href = srtUrl;
    resultPanel.classList.remove("hidden");

    try {
      const res = await fetch(`/api/jobs/${jobId}/agent-outputs`);
      if (res.ok) {
        const data = await res.json();
        agentOutputsJson.textContent = JSON.stringify(data.scenes, null, 2);
      }
    } catch (_) {
      agentOutputsJson.textContent = "(Could not load agent outputs)";
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    startJob();
  });

  retryBtn.addEventListener("click", () => {
    startJob();
  });

  resetBtn.addEventListener("click", () => {
    clearPoll();
    currentJobId = null;
    setBusy(false);
    hideError();
    hideResult();
    progressPanel.classList.add("hidden");
    statusText.textContent = "Queued";
    
    // Reset spinner classes
    const spinnerContainer = document.querySelector(".spinner-container");
    if (spinnerContainer) {
      spinnerContainer.classList.remove("is-done", "is-failed");
    }
    
    // Reset agent checklist
    document.querySelectorAll(".agent-item").forEach((item) => {
      item.classList.remove("is-running", "is-completed", "is-failed");
      const label = item.querySelector(".agent-status");
      if (label) label.textContent = "Pending";
    });
  });

  // Changing creative settings should start a new reel, not resume the old one.
  ["prompt", "duration", "style", "platform", "voice"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("change", () => {
        currentJobId = null;
      });
    }
  });
  document.querySelectorAll('input[name="dev_mode"]').forEach((el) => {
    el.addEventListener("change", () => {
      currentJobId = null;
    });
  });
})();
