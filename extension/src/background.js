/**
 * Trivor — LinkedIn Profile Exporter
 * Service Worker (Background Script) — Manifest V3
 */

'use strict';

chrome.runtime.onInstalled.addListener(() => {
  console.log('[Trivor Exporter] Extensão instalada com sucesso.');
});

// Listener de requisições vindas do popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'PING') {
    sendResponse({ status: 'PONG' });
    return true;
  }

  if (request.action === 'GET_ACTIVE_TAB') {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs && tabs.length > 0) {
        sendResponse({ tab: tabs[0] });
      } else {
        sendResponse({ tab: null });
      }
    });
    return true;
  }
});