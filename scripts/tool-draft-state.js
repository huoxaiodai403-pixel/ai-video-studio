/* Browser storage transactions for the single-step editors; no DOM dependencies. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ToolDraftState = api;
})(typeof globalThis === 'object' ? globalThis : this, () => {
  'use strict';
  const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  function check(value) {
    if (!record(value) || (value.data !== undefined && !record(value.data)) ||
        (value.selected !== undefined && typeof value.selected !== 'string') ||
        (value.saved_at !== undefined && typeof value.saved_at !== 'string') ||
        (value.submitted !== undefined && (!record(value.submitted) ||
          Object.values(value.submitted).some(row => typeof row !== 'string')))) {
      throw Error('Invalid tool draft');
    }
    return value;
  }
  function open(storage, key) {
    const resolve = typeof storage === 'function' ? storage : () => storage;
    const state = {}, originals = new Set();
    let baseline = null, known = false, issue = null, recoveryError = '';
    function preserve(raw) { if (typeof raw === 'string') originals.add(raw); }
    function block(reason) {
      preserve(baseline);
      // A quota error must not weaken an existing conflict/corruption guard.
      if (!issue || issue === 'write') issue = reason;
      return false;
    }
    try {
      baseline = resolve().getItem(key); known = true;
      if (baseline !== null) Object.assign(state, check(JSON.parse(baseline)));
    } catch { block(known ? 'corrupt' : 'read'); }
    function inspect() {
      try {
        const raw = resolve().getItem(key);
        if (!known || raw !== baseline) { preserve(raw); return block('conflict'); }
        return true;
      } catch { return block('read'); }
    }
    function encoded() {
      try { return JSON.stringify(check(state)); }
      catch { block('capture'); return null; }
    }
    function save() {
      if (!inspect() || (issue && issue !== 'write')) return false;
      const raw = encoded(); if (raw === null) return false;
      try {
        resolve().setItem(key, raw); baseline = raw;
        issue = null; recoveryError = ''; return true;
      } catch { return block('write'); }
    }
    function recover() {
      if (!issue || issue === 'write') return save();
      const next = encoded(); if (next === null) return false;
      try {
        const target = resolve(), current = target.getItem(key);
        preserve(current);
        const backup = JSON.stringify({schema:1, source:key, saved_at:new Date().toISOString(),
          reason:issue, originals:[...originals], editing:JSON.parse(next)});
        const id = typeof crypto === 'object' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const backupKey = `${key}:recovery:${id}`;
        if (target.getItem(backupKey) !== null) throw Error('Backup already exists');
        target.setItem(backupKey, backup);
        if (target.getItem(backupKey) !== backup) throw Error('Backup was not retained');
        // A second window may have saved while this backup was being prepared.
        if (target.getItem(key) !== current) {
          preserve(target.getItem(key)); issue = 'conflict'; recoveryError = 'changed'; return false;
        }
        target.setItem(key, next); baseline = next; known = true;
        issue = null; recoveryError = ''; return true;
      } catch { recoveryError = 'backup'; return false; }
    }
    function backups() {
      const rows = [];
      try {
        const target = resolve();
        for (let index = 0; index < target.length; index++) {
          const name = target.key(index);
          if (name?.startsWith(`${key}:recovery:`)) rows.push({key:name, raw:target.getItem(name)});
        }
      } catch { /* Download remains available for any entries already read. */ }
      return rows;
    }
    return {state, save, recover, inspect, block,
      get issue() { return issue; },
      get recoveryError() { return recoveryError; },
      originals:() => [...originals], backups};
  }
  return {open, check};
});
