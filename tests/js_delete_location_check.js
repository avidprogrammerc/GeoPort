// Behavioral check of the saved-locations JS in map.html (stubs, no jsdom).
const fs = require('fs');
const html = fs.readFileSync('src/templates/map.html', 'utf8');

// Pull the saved-locations JS section out of the page.
const start = html.indexOf('// ============ Saved location presets');
const end = html.indexOf('// ============ Server info');
if (start < 0 || end < 0) { console.error('section not found'); process.exit(1); }
const src = html.slice(start, end);

let failures = 0;
const assert = (cond, msg) => { if (!cond) { failures++; console.error('FAIL:', msg); } else { console.log('ok  :', msg); } };

function env() {
  const state = {
    fetchCalls: [],
    toasts: [],
    confirmResult: true,
    items: [
      { name: "Parent's", lat: 37.4, lng: -77.6 },
      { name: 'Work (HQ)', lat: 1.0, lng: 2.0 },
    ],
    fetchStatus: 200,
  };
  const select = {
    value: '',
    // pre-populated as loadSavedLocations() would produce it
    _opts: [
      { textContent: 'Saved locations…', value: '' },
      { textContent: "Parent's", value: '37.4,-77.6' },
      { textContent: 'Work (HQ)', value: '1.0,2.0' },
    ],
    selectedIndex: 0,
    appendChild(o) { this._opts.push(o); },
    get options() { return this._opts; },
    set innerHTML(v) {
      // mimic the DOM: replacing innerHTML wipes the option list
      this._inner = v;
      this._opts = [{ textContent: 'Saved locations…', value: '' }];
    },
    get innerHTML() { return this._inner; },
  };
  const button = { disabled: true };

  global.document = {
    getElementById(id) {
      if (id === 'savedLocations') return select;
      if (id === 'deleteLocationBtn') return button;
      return null;
    },
    createElement() {
      const o = {};
      return o; // value/textContent set plainly by loadSavedLocations
    },
  };
  global.window = global;
  global.map = undefined;
  global.marker = undefined;
  global.setCoordinates = () => {};
  global.createMarker = () => {};
  global.displayToast = (m) => state.toasts.push(m);
  global.confirm = () => state.confirmResult;
  global.fetch = (url, opts) => {
    state.fetchCalls.push({ url, opts });
    return Promise.resolve({ ok: state.fetchStatus < 400, status: state.fetchStatus, json: () => Promise.resolve(state.items) });
  };

  // Evaluate the section, then grab the functions.
  const fn = new Function(src + '\nreturn { loadSavedLocations, updateDeleteLocationBtn, deleteSavedLocation };');
  const api = fn();
  return { state, select, button, api };
}

// --- 1: loadSavedLocations populates select and enables delete button -------
{
  const { state, select, button, api } = env();
  api.loadSavedLocations();
  setTimeout(() => {
    assert(select._opts.length === 3, 'load: placeholder + 2 presets in select');
    assert(select._opts[1].textContent === "Parent's", 'load: preset name rendered');
    assert(button.disabled === true, 'load: delete button disabled while no selection');
    select.value = '37.4,-77.6'; select.selectedIndex = 1;
    api.updateDeleteLocationBtn();
    assert(button.disabled === false, 'select: delete button enabled when a preset is selected');
    select.value = '';
    api.updateDeleteLocationBtn();
    assert(button.disabled === true, 'select: delete button disabled again when cleared');
    runDelete();
  }, 20);
}

function runDelete() {
  // --- 2: deleteSavedLocation issues DELETE with encoded name ---------------
  let { state, select, button, api } = env();
  select.value = '37.4,-77.6'; select.selectedIndex = 1;
  api.deleteSavedLocation();
  setTimeout(() => {
    assert(state.fetchCalls.length === 2, 'delete: DELETE fetch + list reload');
    const c = state.fetchCalls[0];
    assert(c.opts && c.opts.method === 'DELETE', 'delete: first fetch is the DELETE');
    assert(state.fetchCalls[1].url === '/locations', 'delete: second fetch reloads the list');
    assert(c.url === '/locations/' + encodeURIComponent("Parent's"), 'delete: URL is /locations/<encoded name> (got ' + c.url + ')');
    assert(select.value === '', 'delete: select reset after success');
    assert(state.toasts[0] === 'Removed "Parent\'s"', 'delete: success toast');
    assert(button.disabled === true, 'delete: button disabled after reset');

    // --- 3: confirm=false -> no fetch ---------------------------------------
    ({ state, select, button, api } = env());
    state.confirmResult = false;
    select.value = '1.0,2.0'; select.selectedIndex = 2;
    api.deleteSavedLocation();
    setTimeout(() => {
      assert(state.fetchCalls.length === 0, 'cancel: confirm=false skips fetch');

      // --- 4: fetch 500 -> error toast, select NOT reset ---------------------
      ({ state, select, button, api } = env());
      state.fetchStatus = 500;
      select.value = '1.0,2.0'; select.selectedIndex = 2;
      api.deleteSavedLocation();
      setTimeout(() => {
        assert(state.toasts[0] === 'Could not remove location', 'error: failure toast on 500');
        assert(select.value === '1.0,2.0', 'error: selection kept on failure (user can retry)');
        process.exit(failures ? 1 : 0);
      }, 20);
    }, 20);
  }, 20);
}
