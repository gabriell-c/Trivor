/**
 * Trivor — LinkedIn Profile Exporter
 * Service Worker (background.js)
 * Apenas para logs e eventos básicos — a orquestração principal está no popup.
 */
"use strict";

chrome.runtime.onInstalled.addListener(() => {
  console.log("[Trivor Exporter] Extensão instalada com sucesso. Versão 3.1.0");
});
