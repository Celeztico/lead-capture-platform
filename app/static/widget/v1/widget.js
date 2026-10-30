/**
 * Lead-Capture Platform — Embeddable Widget (v1)
 *
 * A lightweight, vanilla JavaScript widget that:
 * 1. Finds container elements with data-widget-id
 * 2. Fetches public configuration from the platform API
 * 3. Renders an accessible lead-capture form
 * 4. Submits the form to the public submission endpoint
 *
 * CORS: Works cross-origin when the API allows the embedding origin.
 * Privacy: No secrets or credentials are embedded in this bundle.
 */

(function () {
  "use strict";

  var SELECTOR = '[data-widget-id]';
  var INITIALIZED = new WeakSet();

  // --- Helpers ------------------------------------------------------------

  function getOrigin() {
    if (typeof location !== "undefined" && location.origin) {
      return location.origin;
    }
    return "";
  }

  function getScriptOrigin() {
    // Resolve the API origin from where this script was loaded from, so the
    // widget works when embedded on a different origin than the API.
    // document.currentScript is available while this deferred bundle executes.
    try {
      var script = document.currentScript;
      if (script && script.src) {
        var anchor = document.createElement("a");
        anchor.href = script.src;
        return anchor.origin || anchor.protocol + "//" + anchor.host;
      }
    } catch (e) {
      // fall through to page origin
    }
    return null;
  }

  function createElement(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (attrs[key] === null || attrs[key] === undefined) {
          return;
        }
        el.setAttribute(key, attrs[key]);
      });
    }
    if (children) {
      children.forEach(function (child) {
        if (typeof child === "string") {
          el.appendChild(document.createTextNode(child));
        } else {
          el.appendChild(child);
        }
      });
    }
    return el;
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // --- Fetch wrapper ------------------------------------------------------

  function fetchJson(url, options) {
    return fetch(url, options).then(function (response) {
      if (!response.ok) {
        return response.text().then(function (body) {
          throw new Error("HTTP " + response.status + ": " + body);
        });
      }
      return response.json();
    });
  }

  // --- Rendering ----------------------------------------------------------

  function renderForm(container, config, apiBase) {
    var cfg = config.configuration || {};
    var fields = cfg.fields || [];

    var form = createElement("form", {
      id: "lead-capture-form-" + config.public_widget_id,
      "data-widget-id": config.public_widget_id,
      novalidate: "true",
    });

    // Title
    if (cfg.title) {
      var title = createElement("h2", {}, [cfg.title]);
      form.appendChild(title);
    }

    // Description
    if (cfg.description) {
      var desc = createElement("p", {}, [cfg.description]);
      form.appendChild(desc);
    }

    // Fields
    fields.forEach(function (field) {
      var group = createElement("div", { class: "lc-field" });

      var label = createElement(
        "label",
        { for: "lc-field-" + field.name },
        [escapeHtml(field.label)]
      );
      if (field.required) {
        var req = createElement("span", { class: "lc-required" }, [" *"]);
        label.appendChild(req);
      }
      group.appendChild(label);

      var input;
      if (field.type === "textarea") {
        input = createElement("textarea", {
          id: "lc-field-" + field.name,
          name: field.name,
          required: field.required ? "true" : null,
          placeholder: field.placeholder || "",
        });
      } else {
        input = createElement("input", {
          type: field.type,
          id: "lc-field-" + field.name,
          name: field.name,
          required: field.required ? "true" : null,
          placeholder: field.placeholder || "",
        });
      }
      group.appendChild(input);

      // Error message container (hidden by default)
      var error = createElement("div", {
        class: "lc-error",
        role: "alert",
        style: "display: none;",
      });
      group.appendChild(error);

      form.appendChild(group);
    });

    // Honeypot field (hidden spam control — must remain empty)
    var honeypot = createElement("input", {
      type: "text",
      name: "website_url",
      tabindex: "-1",
      autocomplete: "off",
      style: "display: none !important;",
    });
    form.appendChild(honeypot);

    // Submit button
    var button = createElement(
      "button",
      { type: "submit" },
      [escapeHtml(cfg.submit_label || "Submit")]
    );
    form.appendChild(button);

    // Status message
    var status = createElement("div", {
      id: "lc-status-" + config.public_widget_id,
      class: "lc-status",
      "aria-live": "polite",
    });
    form.appendChild(status);

    container.appendChild(form);

    // --- Submit handler ---------------------------------------------------

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      // Clear previous errors
      form.querySelectorAll(".lc-error").forEach(function (el) {
        el.textContent = "";
        el.style.display = "none";
      });
      form.querySelectorAll("input, textarea").forEach(function (el) {
        el.setAttribute("aria-invalid", "false");
      });

      var statusEl = document.getElementById("lc-status-" + config.public_widget_id);
      statusEl.textContent = "";
      statusEl.className = "lc-status";

      // Collect form data
      var data = {};
      var valid = true;

      fields.forEach(function (field) {
        var el = document.getElementById("lc-field-" + field.name);
        var value = el ? el.value.trim() : "";

        if (field.required && !value) {
          valid = false;
          el.setAttribute("aria-invalid", "true");
          var errorEl = el.parentNode.querySelector(".lc-error");
          if (errorEl) {
            errorEl.textContent = escapeHtml(field.label) + " is required.";
            errorEl.style.display = "block";
          }
        }

        if (value) {
          data[field.name] = value;
        }
      });

      if (!valid) {
        statusEl.textContent = "Please fix the errors above.";
        statusEl.className = "lc-status lc-status-error";
        return;
      }

      // Show loading
      var submitBtn = form.querySelector('button[type="submit"]');
      var originalLabel = submitBtn.textContent;
      submitBtn.textContent = "Sending...";
      submitBtn.disabled = true;

      var submitUrl = apiBase + "/public/v1/widgets/" + config.public_widget_id + "/submissions";

      fetchJson(submitUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: getOrigin(),
        },
        body: JSON.stringify({ data: data }),
        credentials: "omit",
      })
        .then(function (result) {
          statusEl.textContent = result.message || "Thank you! Your submission has been received.";
          statusEl.className = "lc-status lc-status-success";
          form.reset();
        })
        .catch(function (err) {
          statusEl.textContent = "Submission failed. Please try again later.";
          statusEl.className = "lc-status lc-status-error";
          console.error("Widget submission error:", err);
        })
        .finally(function () {
          submitBtn.textContent = originalLabel;
          submitBtn.disabled = false;
        });
    });
  }

  // --- Initialization -----------------------------------------------------

  function initWidget(container) {
    if (INITIALIZED.has(container)) {
      return;
    }
    INITIALIZED.add(container);

    var publicId = container.getAttribute("data-widget-id");

    if (!publicId) {
      console.error("Lead Capture Widget: missing data-widget-id attribute");
      return;
    }

    // API base resolution: explicit data-api-base > script src origin > page origin
    var apiBaseAttr = container.getAttribute("data-api-base");
    var apiBase =
      (apiBaseAttr && apiBaseAttr.replace(/\/$/, "")) || getScriptOrigin() || getOrigin();
    var configUrl = apiBase + "/public/v1/widgets/" + publicId + "/config";

    fetchJson(configUrl, {
      headers: {
        Origin: getOrigin(),
      },
      credentials: "omit",
    })
      .then(function (config) {
        if (config.status !== "active") {
          console.warn(
            "Lead Capture Widget: widget " + publicId + " is not active (status: " + config.status + ")"
          );
          return;
        }
        renderForm(container, config, apiBase);
      })
      .catch(function (err) {
        console.error("Lead Capture Widget: failed to load config for " + publicId, err);
        container.innerHTML =
          '<div style="color:#c00;padding:10px;">Widget unavailable. Please try again later.</div>';
      });
  }

  function initAll() {
    document.querySelectorAll(SELECTOR).forEach(initWidget);
  }

  // --- Bootstrap ----------------------------------------------------------

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }

  // Expose for manual re-initialization
  window.LeadCaptureWidget = {
    init: initAll,
    initContainer: initWidget,
  };
})();