(function () {
  "use strict";

  const API_URL = "http://localhost:8000/suggest-idiom";
  const DEBOUNCE_MS = 1500;
  const FETCH_TIMEOUT_MS = 90000;
  const MAX_CONTEXT_LENGTH = 1200;
  const TARGET_LANGUAGE = "auto";
  const WIDGET_ID = "contextual-idiom-translator-widget";
  const EDITOR_ID = "contextual-idiom-local-file-editor";
  const EDITABLE_SELECTOR = [
    "textarea",
    "input[type='text']",
    "input[type='search']",
    "input[type='email']",
    "input[type='url']",
    "input[type='tel']",
    "input:not([type])",
    "[contenteditable='']",
    "[contenteditable='true']",
    "[contenteditable='plaintext-only']"
  ].join(", ");

  const SENTENCE_BOUNDARY = /[.!?\n\r]/;
  const KNOWN_IDIOM_PATTERN =
      /\b(?:kick the bucket|piece of cake|break a leg|spill the beans|under the weather|raining cats and dogs|costs an arm and a leg|hit the sack|let the cat out of the bag|once in a blue moon|bite the bullet|the ball is in your court|pulling my leg|on thin ice|burning the midnight oil|the last straw|break the ice|cut corners|hit the nail on the head|through thick and thin|when pigs fly|beat around the bush|call it a day|get cold feet|miss the boat|add fuel to the fire)\b/i;
  const ROUGH_CUE_PATTERN =
      /\b(?:idiom|saying|proverb|literally|in my language|we say|they say|sounds like|as if|like|roughly|translate|means)\b/i;

  let debounceTimer = null;
  let activeRequestId = 0;
  let activeCandidate = null;
  let lastCandidateKey = "";
  let currentSuggestions = [];
  let currentMessage = "";
  let panelOpen = false;
  let loading = false;

  function isEditableElement(element) {
    if (!element || element.nodeType !== Node.ELEMENT_NODE) {
      return false;
    }

    if (!element.matches(EDITABLE_SELECTOR) && !element.isContentEditable) {
      return false;
    }

    if (element instanceof HTMLInputElement) {
      const type = (element.getAttribute("type") || "text").toLowerCase();
      const blockedTypes = new Set([
        "button", "checkbox", "color", "date", "datetime-local", "file", "hidden", "image",
        "month", "number", "password", "radio", "range", "reset", "submit", "time", "week"
      ]);
      return !blockedTypes.has(type) && !element.disabled && !element.readOnly;
    }

    if (element instanceof HTMLTextAreaElement) {
      return !element.disabled && !element.readOnly;
    }

    return true;
  }

  function resolveEditableRoot(element) {
    if (!element || element.nodeType !== Node.ELEMENT_NODE) {
      return null;
    }
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      return isEditableElement(element) ? element : null;
    }
    const explicitEditable = element.closest("[contenteditable=''], [contenteditable='true'], [contenteditable='plaintext-only']");
    if (explicitEditable && isEditableElement(explicitEditable)) {
      return explicitEditable;
    }
    return isEditableElement(element) ? element : null;
  }

  function makeLocalTextPageEditable() {
    if (document.getElementById(EDITOR_ID)) {
      return;
    }
    const hasEditable = document.querySelector(EDITABLE_SELECTOR);
    const isSinglePre = document.body?.children.length === 1 && document.body.firstElementChild?.tagName === "PRE";
    const looksLikeTextFile = location.protocol === "file:" || document.contentType === "text/plain" || isSinglePre;
    if (hasEditable || !looksLikeTextFile || !document.body) {
      return;
    }

    const sourceText = document.body.innerText || "";
    document.body.innerHTML = "";
    document.body.style.margin = "0";
    document.body.style.background = "#f6f7fb";

    const editor = document.createElement("div");
    editor.id = EDITOR_ID;
    editor.contentEditable = "true";
    editor.spellcheck = true;
    editor.textContent = sourceText || "Type here. Try: I would go out but [esta lloviendo a cantaros]";
    editor.style.minHeight = "100vh";
    editor.style.boxSizing = "border-box";
    editor.style.padding = "32px";
    editor.style.outline = "none";
    editor.style.whiteSpace = "pre-wrap";
    editor.style.font = "16px/1.6 Consolas, 'Courier New', monospace";
    editor.style.color = "#172033";
    editor.style.background = "#ffffff";
    document.body.appendChild(editor);
    editor.focus();
  }

  function findEditableFromEvent(event) {
    const path = typeof event.composedPath === "function" ? event.composedPath() : [];
    for (const node of path) {
      if (node instanceof Element) {
        const editable = resolveEditableRoot(node);
        if (editable) {
          return editable;
        }
      }
    }
    return document.activeElement ? resolveEditableRoot(document.activeElement) : null;
  }

  function normalizeWhitespace(value) {
    return value.replace(/\s+/g, " ").trim();
  }

  function findSentenceBounds(text, caretIndex) {
    const boundedCaret = Math.max(0, Math.min(caretIndex, text.length));
    let start = boundedCaret;
    while (start > 0 && !SENTENCE_BOUNDARY.test(text.charAt(start - 1))) {
      start -= 1;
    }
    let end = boundedCaret;
    while (end < text.length && !SENTENCE_BOUNDARY.test(text.charAt(end))) {
      end += 1;
    }
    while (start < end && /\s/.test(text.charAt(start))) {
      start += 1;
    }
    while (end > start && /\s/.test(text.charAt(end - 1))) {
      end -= 1;
    }
    return { start, end };
  }

  function detectRoughPhrase(sentence) {
    const bracketMatch = sentence.match(/\[([^\]]{2,300})\]/);
    if (bracketMatch) {
      return {
        displayText: bracketMatch[0],
        phraseText: bracketMatch[1].trim(),
        start: bracketMatch.index,
        end: bracketMatch.index + bracketMatch[0].length,
        reason: "bracketed"
      };
    }

    const idiomMatch = sentence.match(KNOWN_IDIOM_PATTERN);
    if (idiomMatch) {
      return {
        displayText: idiomMatch[0],
        phraseText: idiomMatch[0],
        start: idiomMatch.index,
        end: idiomMatch.index + idiomMatch[0].length,
        reason: "known-idiom"
      };
    }

    const words = sentence.match(/\b[\p{L}\p{N}'-]+\b/gu) || [];
    if (ROUGH_CUE_PATTERN.test(sentence) && words.length >= 3 && words.length <= 40) {
      return {
        displayText: sentence,
        phraseText: sentence,
        start: 0,
        end: sentence.length,
        reason: "rough-cue"
      };
    }

    return null;
  }

  function getContentEditableText(element) {
    return element.textContent || "";
  }

  function getTextNodeOffsetWithin(root, targetNode, targetOffset) {
    let offset = 0;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      if (node === targetNode) {
        return offset + targetOffset;
      }
      offset += node.nodeValue.length;
      node = walker.nextNode();
    }
    return getContentEditableText(root).length;
  }

  function getContentEditableCaretIndex(element) {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) {
      return getContentEditableText(element).length;
    }
    const range = selection.getRangeAt(0);
    if (!element.contains(range.startContainer)) {
      return getContentEditableText(element).length;
    }
    if (range.startContainer.nodeType === Node.TEXT_NODE) {
      return getTextNodeOffsetWithin(element, range.startContainer, range.startOffset);
    }
    const clonedRange = range.cloneRange();
    clonedRange.selectNodeContents(element);
    clonedRange.setEnd(range.startContainer, range.startOffset);
    return clonedRange.toString().length;
  }

  function readEditableState(element) {
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      const text = element.value;
      const caretIndex = typeof element.selectionStart === "number" ? element.selectionStart : text.length;
      const sentenceBounds = findSentenceBounds(text, caretIndex);
      return {
        element,
        mode: "form",
        text,
        caretIndex,
        sentence: text.slice(sentenceBounds.start, sentenceBounds.end),
        sentenceStart: sentenceBounds.start,
        sentenceEnd: sentenceBounds.end
      };
    }
    const text = getContentEditableText(element);
    const caretIndex = getContentEditableCaretIndex(element);
    const sentenceBounds = findSentenceBounds(text, caretIndex);
    return {
      element,
      mode: "contenteditable",
      text,
      caretIndex,
      sentence: text.slice(sentenceBounds.start, sentenceBounds.end),
      sentenceStart: sentenceBounds.start,
      sentenceEnd: sentenceBounds.end
    };
  }

  function contextWindow(text, start, end) {
    const halfWindow = Math.floor(MAX_CONTEXT_LENGTH / 2);
    return `${text.slice(Math.max(0, start - halfWindow), start)}${text.slice(start, end)}${text.slice(end, Math.min(text.length, end + halfWindow))}`.trim();
  }

  function scheduleSuggestion(event) {
    const element = findEditableFromEvent(event);
    if (!element) {
      return;
    }
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      requestSuggestionForElement(element);
    }, DEBOUNCE_MS);
  }

  async function requestAiSuggestions(payload) {
    const abortController = new AbortController();
    const timeoutId = window.setTimeout(() => abortController.abort(), FETCH_TIMEOUT_MS);
    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload),
        signal: abortController.signal
      });
      if (!response.ok) {
        return {
          suggestions: [],
          message: `AI backend returned ${response.status}.`
        };
      }
      const data = await response.json();
      return {
        suggestions: Array.isArray(data.suggestions) ? data.suggestions : [],
        message: data.fallback_message || ""
      };
    } catch (error) {
      return {
        suggestions: [],
        message: "AI backend is not connected. Start the backend and Ollama, then keep typing."
      };
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  async function requestSuggestionForElement(element) {
    if (!document.contains(element) || !isEditableElement(element)) {
      return;
    }

    const state = readEditableState(element);
    const sentence = normalizeWhitespace(state.sentence);
    if (!sentence) {
      hideWidget();
      return;
    }

    const roughPhrase = detectRoughPhrase(state.sentence);
    if (!roughPhrase) {
      hideWidget();
      return;
    }

    const absoluteStart = state.sentenceStart + roughPhrase.start;
    const absoluteEnd = state.sentenceStart + roughPhrase.end;
    const contextText = contextWindow(state.text, state.sentenceStart, state.sentenceEnd);
    const requestKey = `${roughPhrase.phraseText}|${absoluteStart}|${absoluteEnd}|${TARGET_LANGUAGE}`;

    activeCandidate = {
      element,
      mode: state.mode,
      start: absoluteStart,
      end: absoluteEnd,
      roughText: roughPhrase.displayText
    };

    if (requestKey === lastCandidateKey) {
      showWidget(element);
      return;
    }
    lastCandidateKey = requestKey;

    loading = true;
    currentSuggestions = [];
    currentMessage = "Wait time longer than usual. Searching for suggestions...";
    panelOpen = true;
    showWidget(element);

    const requestId = ++activeRequestId;
    const result = await requestAiSuggestions({
      context_text: contextText,
      phrase: roughPhrase.phraseText,
      target_language: TARGET_LANGUAGE,
      tone_hint: "Infer target language from the surrounding sentence and match its tone."
    });

    if (requestId !== activeRequestId || !activeCandidate || activeCandidate.element !== element) {
      return;
    }

    loading = false;
    currentSuggestions = result.suggestions
      .filter((suggestion) => suggestion && typeof suggestion.suggested_idiom === "string" && suggestion.suggested_idiom.trim())
      .slice(0, 5);
    currentMessage = result.message || (currentSuggestions.length > 0 ? "" : "AI did not return suggestions for this phrase.");
    panelOpen = true;
    showWidget(element);
  }

  function createWidget() {
    let widget = document.getElementById(WIDGET_ID);
    if (widget) {
      return widget;
    }

    widget = document.createElement("section");
    widget.id = WIDGET_ID;
    widget.setAttribute("role", "dialog");
    widget.setAttribute("aria-label", "Idiom suggestions");
    widget.style.position = "fixed";
    widget.style.zIndex = "2147483647";
    widget.style.width = "360px";
    widget.style.maxWidth = "calc(100vw - 24px)";
    widget.style.display = "none";
    widget.style.color = "#172033";
    widget.style.font = "13px/1.4 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
    widget.style.userSelect = "none";
    widget.style.pointerEvents = "none";
    document.documentElement.appendChild(widget);
    return widget;
  }

  function renderWidget() {
    const widget = createWidget();
    widget.innerHTML = "";

    const panel = document.createElement("div");
    panel.style.display = panelOpen ? "block" : "none";
    panel.style.marginBottom = "8px";
    panel.style.padding = "10px";
    panel.style.border = "1px solid rgba(15, 23, 42, 0.15)";
    panel.style.borderRadius = "8px";
    panel.style.background = "#ffffff";
    panel.style.boxShadow = "0 18px 48px rgba(15, 23, 42, 0.22)";
    panel.style.pointerEvents = "auto";

    const header = document.createElement("header");
    header.style.display = "flex";
    header.style.alignItems = "center";
    header.style.justifyContent = "space-between";
    header.style.gap = "8px";
    header.style.marginBottom = "8px";

    const title = document.createElement("strong");
    title.textContent = "Idioms:";
    title.style.fontSize = "13px";
    title.style.color = "#111827";
    header.appendChild(title);

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.textContent = "x";
    closeButton.setAttribute("aria-label", "Close idiom suggestions");
    closeButton.style.width = "24px";
    closeButton.style.height = "24px";
    closeButton.style.border = "0";
    closeButton.style.borderRadius = "6px";
    closeButton.style.background = "#eef2f7";
    closeButton.style.color = "#374151";
    closeButton.style.cursor = "pointer";
    closeButton.addEventListener("click", hideWidget);
    header.appendChild(closeButton);
    panel.appendChild(header);

    if (currentSuggestions.length === 0) {
      const message = document.createElement("div");
      message.textContent = currentMessage || "AI did not return suggestions.";
      message.style.color = "#4b5563";
      panel.appendChild(message);
    } else {
      if (currentMessage) {
        const sourceNote = document.createElement("div");
        sourceNote.textContent = currentMessage;
        sourceNote.style.margin = "0 0 8px";
        sourceNote.style.padding = "7px 8px";
        sourceNote.style.border = "1px solid #d8deea";
        sourceNote.style.borderRadius = "7px";
        sourceNote.style.background = "#f7f9fc";
        sourceNote.style.color = "#49566f";
        sourceNote.style.fontSize = "12px";
        panel.appendChild(sourceNote);
      }

      currentSuggestions.forEach((suggestion) => {
        const item = document.createElement("article");
        item.style.display = "grid";
        item.style.gridTemplateColumns = "1fr auto";
        item.style.gap = "8px 10px";
        item.style.padding = "9px 0";
        item.style.borderTop = "1px solid #edf1f7";

        const idiom = document.createElement("div");
        idiom.textContent = suggestion.suggested_idiom;
        idiom.style.fontWeight = "700";
        idiom.style.color = "#172033";
        idiom.style.overflowWrap = "anywhere";

        const confidence = Number(suggestion.confidence_score);
        if (Number.isFinite(confidence)) {
          const score = document.createElement("span");
          score.textContent = ` ${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%`;
          score.style.color = "#64748b";
          score.style.fontSize = "12px";
          score.style.fontWeight = "600";
          idiom.appendChild(score);
        }

        const insertButton = document.createElement("button");
        insertButton.type = "button";
        insertButton.textContent = "Insert";
        insertButton.style.alignSelf = "start";
        insertButton.style.border = "0";
        insertButton.style.borderRadius = "6px";
        insertButton.style.padding = "6px 9px";
        insertButton.style.background = "#265dff";
        insertButton.style.color = "#ffffff";
        insertButton.style.fontWeight = "700";
        insertButton.style.cursor = "pointer";
        insertButton.addEventListener("click", () => insertSuggestion(suggestion.suggested_idiom));

        const explanation = document.createElement("div");
        explanation.textContent = suggestion.explanation || "Culturally matched idiom.";
        explanation.style.gridColumn = "1 / -1";
        explanation.style.color = "#526071";
        explanation.style.fontSize = "12px";

        item.appendChild(idiom);
        item.appendChild(insertButton);
        item.appendChild(explanation);
        panel.appendChild(item);
      });
    }

    const dock = document.createElement("div");
    dock.style.display = "flex";
    dock.style.alignItems = "center";
    dock.style.justifyContent = "flex-end";
    dock.style.gap = "7px";
    dock.style.pointerEvents = "none";

    const badge = document.createElement("button");
    badge.type = "button";
    badge.setAttribute("aria-label", "Open idiom suggestions");
    badge.style.display = "inline-flex";
    badge.style.alignItems = "center";
    badge.style.gap = "7px";
    badge.style.height = "44px";
    badge.style.padding = "4px 8px";
    badge.style.border = "1px solid rgba(31, 41, 55, 0.16)";
    badge.style.borderRadius = "999px";
    badge.style.background = "#ffffff";
    badge.style.boxShadow = "0 10px 24px rgba(15, 23, 42, 0.18)";
    badge.style.cursor = "pointer";
    badge.style.pointerEvents = "auto";
    badge.addEventListener("click", () => {
      panelOpen = !panelOpen;
      showWidget(activeCandidate?.element);
    });

    const icon = document.createElement("span");
    icon.textContent = "ID";
    icon.style.display = "inline-flex";
    icon.style.alignItems = "center";
    icon.style.justifyContent = "center";
    icon.style.width = "26px";
    icon.style.height = "26px";
    icon.style.borderRadius = "999px";
    icon.style.background = "#8A5997FF";
    icon.style.color = "#ffffff";
    icon.style.fontWeight = "800";
    icon.style.fontSize = "12px";
    badge.appendChild(icon);

    const count = document.createElement("span");
    count.textContent = loading ? "..." : currentSuggestions.length > 0 ? String(currentSuggestions.length) : "!";
    count.style.display = "inline-flex";
    count.style.alignItems = "center";
    count.style.justifyContent = "center";
    count.style.minWidth = "32px";
    count.style.width = loading ? "40px" : "32px";
    count.style.height = "32px";
    count.style.border = "3px solid #ef4d73";
    count.style.borderRadius = "999px";
    count.style.color = "#172033";
    count.style.fontWeight = "800";
    count.style.fontSize = loading ? "13px" : "16px";
    badge.appendChild(count);

    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.textContent = "...";
    dismiss.setAttribute("aria-label", "Close idiom widget");
    dismiss.style.display = "inline-flex";
    dismiss.style.alignItems = "center";
    dismiss.style.justifyContent = "center";
    dismiss.style.width = "30px";
    dismiss.style.height = "30px";
    dismiss.style.border = "1px solid rgba(31, 41, 55, 0.14)";
    dismiss.style.borderRadius = "999px";
    dismiss.style.background = "#ffffff";
    dismiss.style.boxShadow = "0 8px 18px rgba(15, 23, 42, 0.16)";
    dismiss.style.color = "#64748b";
    dismiss.style.fontWeight = "800";
    dismiss.style.cursor = "pointer";
    dismiss.style.pointerEvents = "auto";
    dismiss.addEventListener("click", hideWidget);

    dock.appendChild(badge);
    dock.appendChild(dismiss);
    widget.appendChild(panel);
    widget.appendChild(dock);
  }

  function getEditorRect(element) {
    if (!element || !document.contains(element)) {
      return null;
    }
    const rect = element.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0 ? rect : null;
  }

  function positionWidget(element) {
    const widget = document.getElementById(WIDGET_ID);
    const rect = getEditorRect(element);
    if (!widget || !rect) {
      return;
    }
    const viewportPadding = 12;
    const width = Math.min(360, window.innerWidth - viewportPadding * 2);
    const left = Math.max(viewportPadding, Math.min(window.innerWidth - width - viewportPadding, rect.right - width - 8));
    const top = Math.max(viewportPadding, Math.min(window.innerHeight - 54, rect.bottom - 54));
    widget.style.width = `${width}px`;
    widget.style.left = `${left}px`;
    widget.style.top = `${top}px`;
  }

  function showWidget(element) {
    if (!element) {
      return;
    }
    const widget = createWidget();
    renderWidget();
    widget.style.display = "block";
    positionWidget(element);
  }

  function hideWidget() {
    const widget = document.getElementById(WIDGET_ID);
    if (widget) {
      widget.style.display = "none";
      widget.innerHTML = "";
    }
    currentSuggestions = [];
    currentMessage = "";
    panelOpen = false;
    loading = false;
  }

  function findTextPosition(root, absoluteOffset) {
    let currentOffset = 0;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const nextOffset = currentOffset + node.nodeValue.length;
      if (absoluteOffset <= nextOffset) {
        return {
          node,
          offset: Math.max(0, absoluteOffset - currentOffset)
        };
      }
      currentOffset = nextOffset;
      node = walker.nextNode();
    }
    return null;
  }

  function replaceContentEditableText(element, start, end, replacement) {
    element.focus();
    const startPosition = findTextPosition(element, start);
    const endPosition = findTextPosition(element, end);
    if (!startPosition || !endPosition) {
      document.execCommand("insertText", false, replacement);
      return;
    }
    const range = document.createRange();
    range.setStart(startPosition.node, startPosition.offset);
    range.setEnd(endPosition.node, endPosition.offset);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    if (!document.execCommand("insertText", false, replacement)) {
      range.deleteContents();
      range.insertNode(document.createTextNode(replacement));
      selection.removeAllRanges();
    }
    element.dispatchEvent(new InputEvent("input", {
      bubbles: true,
      inputType: "insertReplacementText",
      data: replacement
    }));
  }

  function insertSuggestion(value) {
    if (!activeCandidate || !activeCandidate.element || !document.contains(activeCandidate.element)) {
      hideWidget();
      return;
    }
    const replacement = value.trim();
    if (!replacement) {
      return;
    }
    const element = activeCandidate.element;
    if (activeCandidate.mode === "form" && (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement)) {
      element.focus();
      const start = Math.max(0, Math.min(activeCandidate.start, element.value.length));
      const end = Math.max(start, Math.min(activeCandidate.end, element.value.length));
      element.setRangeText(replacement, start, end, "end");
      element.dispatchEvent(new InputEvent("input", {
        bubbles: true,
        inputType: "insertReplacementText",
        data: replacement
      }));
    } else {
      replaceContentEditableText(element, activeCandidate.start, activeCandidate.end, replacement);
    }
    activeCandidate = null;
    lastCandidateKey = "";
    hideWidget();
  }

  function repositionActiveWidget() {
    if (activeCandidate && activeCandidate.element && document.contains(activeCandidate.element)) {
      positionWidget(activeCandidate.element);
    }
  }

  makeLocalTextPageEditable();
  document.addEventListener("input", scheduleSuggestion, true);
  document.addEventListener("keyup", scheduleSuggestion, true);
  document.addEventListener("focusin", scheduleSuggestion, true);
  document.addEventListener("scroll", repositionActiveWidget, true);
  window.addEventListener("resize", repositionActiveWidget);
  document.addEventListener("selectionchange", () => {
    const widget = document.getElementById(WIDGET_ID);
    if (widget && document.activeElement && widget.contains(document.activeElement)) {
      return;
    }
    if (!document.activeElement || !resolveEditableRoot(document.activeElement)) {
      hideWidget();
    }
  });
})();
