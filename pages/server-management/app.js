const bridge = window.AstrBotPluginPage;
const state = {
  bindings: [],
  subscriptions: [],
  aliases: [],
  kungfu: [],
  servers: [],
  events: {},
  free_event_actions: [],
  legacy_bilei: [],
  token_stats: null,
  cache: {
    defaults: { api: 300, image: 300 },
    limits: { api_memory_max_mb: 16, api_max_entries: 1024, image_max_mb: 512 },
    api: [],
    images: [],
    stats: {},
  },
  access: { mode: "all", private_allowed: true, reply_on_deny: false, entries: [], recent_groups: [] },
};
const editing = { bindingSession: null, aliasServer: null, kungfuPzid: null, subscriptionSession: null };
let subscriptionSaving = false;
const restoreConfirmationTimers = new WeakMap();
let toastTimer;

const byId = (id) => document.getElementById(id);

function formatUsageCount(value) {
  return Number.isSafeInteger(value) && value >= 0
    ? value.toLocaleString("zh-CN")
    : "—";
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function renderTokenStats() {
  const stats = state.token_stats;
  byId("token-level").textContent = Number.isSafeInteger(stats?.level)
    ? `LV.${stats.level}`
    : "—";
  byId("token-used").textContent = formatUsageCount(stats?.used);
  byId("token-remaining").textContent = formatUsageCount(stats?.remaining);

  const status = byId("token-valid");
  status.classList.remove("token-status--valid", "token-status--invalid");
  if (stats?.valid === true) {
    status.textContent = "有效";
    status.classList.add("token-status--valid");
  } else if (stats?.valid === false) {
    status.textContent = "无效";
    status.classList.add("token-status--invalid");
  } else {
    status.textContent = "未获取";
  }
}

function showToast(message, isError = false) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("is-error", isError);
  toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2600);
}

function button(label, className, onClick) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = `link-button ${className || ""}`.trim();
  element.textContent = label;
  element.addEventListener("click", onClick);
  return element;
}

// 面板的 iframe 沙箱未开放 allow-modals，原生 window.confirm 被静默禁用，
// 因此删除类操作改用页内两步确认：第一次点击进入待确认态，3 秒内再点才执行。
function confirmButton(label, className, onConfirm, armedLabel = "确认删除") {
  let resetTimer;
  const reset = () => {
    clearTimeout(resetTimer);
    element.dataset.armed = "";
    element.classList.remove("link-button--armed");
    element.textContent = label;
  };
  const element = button(label, className, async () => {
    if (element.dataset.armed !== "1") {
      element.dataset.armed = "1";
      element.classList.add("link-button--armed");
      element.textContent = armedLabel;
      clearTimeout(resetTimer);
      resetTimer = setTimeout(reset, 3000);
      return;
    }
    reset();
    await onConfirm();
  });
  return element;
}

function emptyRow(columnCount, message) {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = columnCount;
  cell.className = "empty";
  cell.textContent = message;
  row.append(cell);
  return row;
}

function aliasText(aliases) {
  return aliases.length ? aliases.join("、") : "无";
}

function inlineAliasEditor(aliases, label, onSave, onCancel) {
  const input = document.createElement("input");
  input.className = "inline-editor";
  input.value = aliases.join(", ");
  input.placeholder = "多个别名用逗号分隔";
  input.setAttribute("aria-label", label);

  const saveButton = button("保存", "", async () => {
    saveButton.disabled = true;
    cancelButton.disabled = true;
    const saved = await onSave(input.value);
    if (!saved) {
      saveButton.disabled = false;
      cancelButton.disabled = false;
      input.focus();
    }
  });
  const cancelButton = button("取消", "", onCancel);

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveButton.click();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelButton.click();
    }
  });
  queueMicrotask(() => input.focus());
  return { input, controls: [saveButton, cancelButton] };
}

function createServerSelect(selectedServer = "", label = "绑定区服") {
  const select = document.createElement("select");
  select.className = "inline-editor";
  select.required = true;
  select.setAttribute("aria-label", label);

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "请选择标准区服";
  placeholder.disabled = true;
  placeholder.defaultSelected = true;
  select.append(placeholder);

  state.servers.forEach((server) => {
    const option = document.createElement("option");
    option.value = server;
    option.textContent = server;
    select.append(option);
  });
  select.value = state.servers.includes(selectedServer) ? selectedServer : "";
  return select;
}

function inlineServerEditor(item, onSave, onCancel) {
  const select = createServerSelect(item.server, `${item.session_id}的绑定区服`);
  const saveButton = button("保存", "", async () => {
    if (!select.reportValidity()) return;
    select.disabled = true;
    saveButton.disabled = true;
    cancelButton.disabled = true;
    const saved = await onSave(select.value);
    if (!saved) {
      select.disabled = false;
      saveButton.disabled = false;
      cancelButton.disabled = false;
      select.focus();
    }
  });
  const cancelButton = button("取消", "", onCancel);
  select.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveButton.click();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelButton.click();
    }
  });
  queueMicrotask(() => select.focus());
  return { select, controls: [saveButton, cancelButton] };
}

function bindingMap() {
  return new Map(state.bindings.map((item) => [item.session_id, item.server]));
}

function renderSummary() {
  byId("access-entry-count").textContent = String(state.access.entries.length);
}

function renderServerOptions() {
  const select = byId("binding-server");
  const currentValue = select.value;
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "请选择标准区服";
  placeholder.disabled = true;
  placeholder.defaultSelected = true;
  select.replaceChildren(placeholder, ...state.servers.map((server) => {
    const option = document.createElement("option");
    option.value = server;
    option.textContent = server;
    return option;
  }));
  select.value = state.servers.includes(currentValue) ? currentValue : "";
}

function renderSessionOptions() {
  const sessionIds = new Set([
    ...state.bindings.map((item) => item.session_id),
    ...state.subscriptions.map((item) => item.session_id),
  ]);
  byId("session-options").replaceChildren(...[...sessionIds].sort().map((sessionId) => {
    const option = document.createElement("option");
    option.value = sessionId;
    return option;
  }));
}


function renderBindings() {
  const body = byId("bindings-body");
  if (!state.bindings.length) {
    body.replaceChildren(emptyRow(3, "暂无会话绑定"));
    return;
  }
  body.replaceChildren(...state.bindings.map((item) => {
    const row = document.createElement("tr");
    const session = document.createElement("td");
    const server = document.createElement("td");
    const actions = document.createElement("td");
    session.dataset.label = "会话 ID";
    server.dataset.label = "绑定区服";
    actions.dataset.label = "操作";
    session.textContent = item.session_id;
    actions.className = "actions";
    if (editing.bindingSession === item.session_id) {
      row.classList.add("is-editing");
      const editor = inlineServerEditor(
        item,
        async (selectedServer) => {
          editing.bindingSession = null;
          const saved = await mutate(
            "bindings/save",
            { session_id: item.session_id, server: selectedServer },
            "绑定信息已保存",
          );
          if (!saved) {
            editing.bindingSession = item.session_id;
            renderBindings();
          }
          return saved;
        },
        () => {
          editing.bindingSession = null;
          renderBindings();
        },
      );
      server.append(editor.select);
      actions.append(...editor.controls);
    } else {
      server.textContent = item.server;
      actions.append(
        button("编辑", "", () => {
          editing.bindingSession = item.session_id;
          renderBindings();
        }),
        button("解除绑定", "link-button--danger", async (event) => {
          const control = event.currentTarget;
          control.disabled = true;
          const deleted = await mutate(
            "bindings/delete",
            { session_id: item.session_id },
            "绑定已解除",
          );
          if (!deleted) control.disabled = false;
        }),
      );
    }
    row.append(session, server, actions);
    return row;
  }));
}

function renderLegacyBilei() {
  const records = state.legacy_bilei || [];
  const body = byId("legacy-bilei-body");
  byId("legacy-bilei-count").textContent = String(records.length);
  if (!records.length) {
    body.replaceChildren(emptyRow(7, "没有待迁移的旧避雷数据"));
    return;
  }

  body.replaceChildren(...records.map((item) => {
    const row = document.createElement("tr");
    const id = document.createElement("td");
    const name = document.createElement("td");
    const note = document.createElement("td");
    const time = document.createElement("td");
    const user = document.createElement("td");
    const target = document.createElement("td");
    const actions = document.createElement("td");
    id.dataset.label = "ID";
    name.dataset.label = "避雷名称";
    note.dataset.label = "避雷备注";
    time.dataset.label = "时间";
    user.dataset.label = "记录人";
    target.dataset.label = "目标会话";
    actions.dataset.label = "操作";
    id.textContent = String(item.id);
    name.textContent = item.name || "—";
    note.textContent = item.text || "—";
    note.className = "legacy-note-cell";
    time.textContent = item.time || "—";
    user.textContent = item.user || "—";
    target.className = "legacy-session-cell";
    actions.className = "actions";

    const sessionInput = document.createElement("input");
    sessionInput.className = "inline-editor";
    sessionInput.maxLength = 512;
    sessionInput.required = true;
    sessionInput.setAttribute("list", "session-options");
    sessionInput.setAttribute("aria-label", `避雷记录 ${item.id} 的目标会话`);
    sessionInput.placeholder = "选择已有会话或直接输入";
    target.append(sessionInput);

    const migrateButton = button("迁移", "", async () => {
      if (!sessionInput.reportValidity()) return;
      sessionInput.disabled = true;
      migrateButton.disabled = true;
      const migrated = await mutate(
        "bilei/legacy/migrate",
        { id: item.id, session_id: sessionInput.value },
        `避雷记录 ${item.id} 已迁移`,
      );
      if (!migrated) {
        sessionInput.disabled = false;
        migrateButton.disabled = false;
        sessionInput.focus();
      }
    });
    sessionInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        migrateButton.click();
      }
    });
    actions.append(migrateButton);
    row.append(id, name, note, time, user, target, actions);
    return row;
  }));
}

function openSubscriptionEditor(item = null) {
  if (subscriptionSaving) return;
  editing.subscriptionSession = item?.session_id ?? null;
  const form = byId("subscription-form");
  form.reset();
  byId("subscription-editor-title").textContent = item ? "编辑推送配置" : "添加推送会话";
  const sessionInput = byId("subscription-session");
  sessionInput.value = item?.session_id || "";
  sessionInput.readOnly = Boolean(item);
  byId("subscription-enabled").checked = item?.enabled ?? false;

  const selected = new Set(item?.actions || []);
  const freeActions = new Set(state.free_event_actions);
  const groups = [
    { title: "免费事件", free: true },
    { title: "令牌事件", free: false },
  ];
  byId("subscription-events").replaceChildren(...groups.map((group) => {
    const fieldset = document.createElement("fieldset");
    fieldset.className = "subscription-event-group";
    const legend = document.createElement("legend");
    legend.textContent = group.title;
    const grid = document.createElement("div");
    grid.className = "subscription-event-grid";
    Object.entries(state.events).forEach(([action, name]) => {
      if (freeActions.has(Number(action)) !== group.free) return;
      const label = document.createElement("label");
      label.className = "subscription-choice";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "subscription_action";
      input.value = action;
      input.checked = selected.has(Number(action));
      const text = document.createElement("span");
      text.textContent = `${action} ${name}`;
      label.append(input, text);
      grid.append(label);
    });
    fieldset.append(legend, grid);
    return fieldset;
  }));
  updateSubscriptionSelectionCount();
  form.hidden = false;
  form.scrollIntoView({ block: "nearest" });
  (item ? byId("subscription-enabled") : sessionInput).focus({ preventScroll: true });
}

function updateSubscriptionSelectionCount() {
  const count = byId("subscription-events").querySelectorAll("input:checked").length;
  byId("subscription-selection-count").textContent = `已选择 ${count} 项`;
}

function renderSubscriptions() {
  const body = byId("subscriptions-body");
  const bindings = bindingMap();
  if (!state.subscriptions.length) {
    body.replaceChildren(emptyRow(5, "暂无事件订阅会话，点击“添加推送会话”开始配置"));
    return;
  }
  body.replaceChildren(...state.subscriptions.map((item) => {
    const row = document.createElement("tr");
    const session = document.createElement("td");
    const server = document.createElement("td");
    const enabled = document.createElement("td");
    const actions = document.createElement("td");
    const controls = document.createElement("td");
    session.dataset.label = "会话 ID";
    server.dataset.label = "绑定区服";
    enabled.dataset.label = "总开关";
    actions.dataset.label = "已订阅事件";
    controls.dataset.label = "操作";
    controls.className = "actions";
    session.className = "subscription-session-cell";
    session.textContent = item.session_id;
    server.textContent = bindings.get(item.session_id) || "未绑定（全部区服）";
    const stateLabel = document.createElement("span");
    stateLabel.className = `state ${item.enabled ? "state--on" : "state--off"}`;
    stateLabel.textContent = item.enabled ? "开启" : "关闭";
    enabled.append(stateLabel);
    const tags = document.createElement("div");
    tags.className = "tags";
    if (item.actions.length) {
      item.actions.forEach((action) => {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = `${action} ${state.events[String(action)] || "未知事件"}`;
        tags.append(tag);
      });
    } else {
      tags.textContent = "无";
    }
    actions.append(tags);
    controls.append(
      button("编辑", "", () => openSubscriptionEditor(item)),
      button("删除", "link-button--danger", async (event) => {
        if (subscriptionSaving) return;
        const control = event.currentTarget;
        control.disabled = true;
        subscriptionSaving = true;
        byId("subscription-fields").disabled = true;
        byId("add-subscription").disabled = true;
        try {
          const deleted = await mutate(
            "subscriptions/delete",
            { session_id: item.session_id },
            "会话推送配置已删除",
          );
          if (deleted && editing.subscriptionSession === item.session_id) {
            byId("subscription-form").hidden = true;
            editing.subscriptionSession = null;
          }
        } finally {
          subscriptionSaving = false;
          control.disabled = false;
          byId("subscription-fields").disabled = false;
          byId("add-subscription").disabled = false;
        }
      }),
    );
    row.append(session, server, enabled, actions, controls);
    return row;
  }));
}

function renderAliases() {
  const body = byId("aliases-body");
  const aliasesByServer = new Map(
    state.aliases.map((item) => [item.server, item.aliases]),
  );
  const servers = [...new Set([
    ...state.servers,
    ...aliasesByServer.keys(),
  ])].sort((left, right) => left.localeCompare(right, "zh-CN"));
  if (!servers.length) {
    body.replaceChildren(emptyRow(3, "暂无标准区服数据"));
    return;
  }
  body.replaceChildren(...servers.map((serverName) => {
    const item = {
      server: serverName,
      aliases: aliasesByServer.get(serverName) || [],
    };
    const row = document.createElement("tr");
    const server = document.createElement("td");
    const aliases = document.createElement("td");
    const actions = document.createElement("td");
    server.dataset.label = "标准区服名";
    aliases.dataset.label = "别名";
    actions.dataset.label = "操作";
    server.textContent = item.server;
    aliases.className = "alias-cell";
    actions.className = "actions";
    if (editing.aliasServer === item.server) {
      row.classList.add("is-editing");
      const editor = inlineAliasEditor(
        item.aliases,
        `${item.server}的区服别名`,
        async (value) => {
          editing.aliasServer = null;
          const saved = await mutate(
            "aliases/save",
            { server: item.server, aliases: value },
            "区服别名已保存",
          );
          if (!saved) {
            editing.aliasServer = item.server;
            renderAliases();
          }
          return saved;
        },
        () => {
          editing.aliasServer = null;
          renderAliases();
        },
      );
      aliases.append(editor.input);
      actions.append(...editor.controls);
    } else {
      aliases.textContent = aliasText(item.aliases);
      actions.append(button("编辑", "", () => {
        editing.aliasServer = item.server;
        renderAliases();
      }));
    }
    row.append(server, aliases, actions);
    return row;
  }));
}

function renderKungfu() {
  const body = byId("kungfu-body");
  if (!state.kungfu.length) {
    body.replaceChildren(emptyRow(3, "暂无心法配置"));
    return;
  }
  body.replaceChildren(...state.kungfu.map((item) => {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    const aliases = document.createElement("td");
    const actions = document.createElement("td");
    name.dataset.label = "标准心法名";
    aliases.dataset.label = "别名";
    actions.dataset.label = "操作";
    name.textContent = item.name;
    aliases.className = "alias-cell";
    actions.className = "actions";
    if (editing.kungfuPzid === item.pzid) {
      row.classList.add("is-editing");
      const editor = inlineAliasEditor(
        item.aliases,
        `${item.name}的心法别名`,
        async (value) => {
          editing.kungfuPzid = null;
          const saved = await mutate(
            "kungfu/save",
            { pzid: item.pzid, aliases: value },
            "心法别名已保存",
          );
          if (!saved) {
            editing.kungfuPzid = item.pzid;
            renderKungfu();
          }
          return saved;
        },
        () => {
          editing.kungfuPzid = null;
          renderKungfu();
        },
      );
      aliases.append(editor.input);
      actions.append(...editor.controls);
    } else {
      aliases.textContent = aliasText(item.aliases);
      actions.append(button("编辑", "", () => {
        editing.kungfuPzid = item.pzid;
        renderKungfu();
      }));
    }
    row.append(name, aliases, actions);
    return row;
  }));
}

function renderAccessControls() {
  const radio = document.querySelector(`input[name="access-mode"][value="${state.access.mode}"]`);
  if (radio) radio.checked = true;
  byId("access-private").checked = Boolean(state.access.private_allowed);
  byId("access-reply").checked = Boolean(state.access.reply_on_deny);
}

function renderAccessEntries() {
  const body = byId("access-entries-body");
  if (!state.access.entries.length) {
    body.replaceChildren(emptyRow(3, "暂无名单条目 —— 切换为白名单或黑名单模式后，此名单生效"));
    return;
  }
  body.replaceChildren(...state.access.entries.map((item) => {
    const row = document.createElement("tr");
    const key = document.createElement("td");
    const note = document.createElement("td");
    const actions = document.createElement("td");
    key.dataset.label = "会话 ID / 群号";
    note.dataset.label = "备注";
    actions.dataset.label = "操作";
    key.textContent = item.key;
    note.textContent = item.note || "—";
    actions.className = "actions";
    actions.append(
      button("编辑", "", () => {
        byId("access-key").value = item.key;
        byId("access-note").value = item.note || "";
        byId("access-key").focus();
      }),
      confirmButton("删除", "link-button--danger", () =>
        mutate("access/entries/delete", { key: item.key }, "名单条目已删除"),
      ),
    );
    row.append(key, note, actions);
    return row;
  }));
}

function renderAccessKeyOptions() {
  const list = byId("access-key-options");
  const seen = new Set();
  const values = [];
  state.access.recent_groups.forEach((item) => {
    if (!seen.has(item.group_id)) {
      seen.add(item.group_id);
      values.push(item.group_id);
    }
  });
  list.replaceChildren(...values.map((value) => {
    const option = document.createElement("option");
    option.value = value;
    return option;
  }));
}

function renderAccessRecent() {
  const body = byId("access-recent-body");
  if (!state.access.recent_groups.length) {
    const empty = document.createElement("p");
    empty.className = "recent-empty";
    empty.textContent = "暂无记录 —— 群内触发过任意插件指令后，该群会出现在这里，可直接加入名单。";
    body.replaceChildren(empty);
    return;
  }
  const listed = new Set(state.access.entries.map((item) => item.key));
  body.replaceChildren(...state.access.recent_groups.map((item) => {
    const chip = document.createElement("div");
    chip.className = "recent-item";
    const meta = document.createElement("div");
    meta.className = "recent-item__meta";
    const group = document.createElement("strong");
    group.textContent = item.group_id;
    const detail = document.createElement("span");
    detail.textContent = `${item.session_id} · ${item.updated_at}`;
    meta.append(group, detail);
    const addButton = button("加入名单", "", async () => {
      await mutate("access/entries/add", { key: item.group_id, note: "" }, "已加入名单");
    });
    addButton.disabled = listed.has(item.group_id);
    addButton.title = addButton.disabled ? "已在名单中" : "以群号加入当前名单";
    chip.append(meta, addButton);
    return chip;
  }));
}

function cacheSettingRow(cacheType, item) {
  const row = document.createElement("tr");
  const name = document.createElement("td");
  const ttl = document.createElement("td");
  const status = document.createElement("td");
  const actions = document.createElement("td");
  name.dataset.label = cacheType === "api" ? "接口路径" : "图片指令";
  ttl.dataset.label = "缓存时间（秒）";
  status.dataset.label = "配置状态";
  actions.dataset.label = "操作";
  name.textContent = item.name;
  name.className = "cache-name-cell";
  actions.className = "actions";

  const input = document.createElement("input");
  input.className = "inline-editor inline-editor--ttl";
  input.type = "number";
  input.min = "0";
  input.max = "2592000";
  input.step = "1";
  input.required = true;
  input.value = String(item.ttl_seconds);
  input.setAttribute("aria-label", `${item.name}缓存时间（秒）`);
  ttl.append(input);

  const badge = document.createElement("span");
  badge.className = `cache-badge ${item.overridden ? "cache-badge--custom" : ""}`.trim();
  badge.textContent = item.overridden
    ? "独立设置"
    : item.safe_default
      ? "安全默认"
      : "继承默认";
  status.append(badge);

  const saveButton = button("保存", "", async () => {
    if (!input.reportValidity()) return;
    saveButton.disabled = true;
    restoreButton.disabled = true;
    const saved = await mutate(
      "cache/settings/save",
      { cache_type: cacheType, cache_name: item.name, ttl_seconds: Number(input.value) },
      `${item.name}缓存时间已保存`,
    );
    if (!saved) {
      saveButton.disabled = false;
      restoreButton.disabled = false;
    }
  });
  const restoreButton = button("恢复默认", "", async () => {
    restoreButton.disabled = true;
    saveButton.disabled = true;
    const saved = await mutate(
      "cache/settings/save",
      { cache_type: cacheType, cache_name: item.name, inherit: true },
      `${item.name}已恢复默认时间`,
    );
    if (!saved) {
      restoreButton.disabled = false;
      saveButton.disabled = false;
    }
  });
  const clearButton = button("清除此项", "link-button--danger", async () => {
    clearButton.disabled = true;
    const cleared = await mutate(
      "cache/item/clear",
      { cache_type: cacheType, cache_name: item.name },
      `${item.name}缓存已清除，下次调用将重新生成`,
    );
    if (!cleared) clearButton.disabled = false;
  });
  restoreButton.disabled = !item.overridden;
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveButton.click();
    }
  });
  actions.append(saveButton, restoreButton, clearButton);
  row.append(name, ttl, status, actions);
  return row;
}

function renderCacheTable(cacheType) {
  const isApi = cacheType === "api";
  const items = isApi ? state.cache.api : state.cache.images;
  const filter = byId(isApi ? "api-cache-filter" : "image-cache-filter")
    .value.trim().toLocaleLowerCase("zh-CN");
  const visible = items.filter((item) => item.name.toLocaleLowerCase("zh-CN").includes(filter));
  const body = byId(isApi ? "api-cache-settings-body" : "image-cache-settings-body");
  body.replaceChildren(...(
    visible.length
      ? visible.map((item) => cacheSettingRow(cacheType, item))
      : [emptyRow(4, filter ? "没有匹配的缓存项目" : "暂无缓存项目")]
  ));
}

function renderCache() {
  const cache = state.cache || { defaults: {}, limits: {}, api: [], images: [], stats: {} };
  const stats = cache.stats || {};
  const apiDefault = cache.defaults?.api ?? 300;
  const imageDefault = cache.defaults?.image ?? 600;
  const memoryLimitMb = cache.limits?.api_memory_max_mb ?? 16;
  const apiEntryLimit = cache.limits?.api_max_entries ?? stats.api_entry_limit ?? 256;
  const imageLimitMb = cache.limits?.image_max_mb ?? 512;
  byId("api-cache-count").textContent = `${stats.api_count || 0} / ${apiEntryLimit} 条`;
  byId("api-cache-size").textContent = formatBytes(stats.api_size_bytes);
  byId("image-cache-count").textContent = `${stats.image_count || 0} 张`;
  byId("image-cache-size").textContent = `${formatBytes(stats.image_size_bytes)} / ${formatBytes(stats.image_limit_bytes)}`;
  byId("api-default-ttl").value = String(apiDefault);
  byId("image-default-ttl").value = String(imageDefault);
  byId("api-memory-size-limit").value = String(memoryLimitMb);
  byId("api-entry-limit").value = String(apiEntryLimit);
  byId("image-size-limit").value = String(imageLimitMb);
  byId("api-memory-summary").textContent = `${formatBytes(stats.api_memory_size_bytes)} / ${formatBytes(stats.api_memory_limit_bytes)}`;
  byId("api-memory-count").textContent = `${stats.api_memory_count || 0} 条，最久未使用优先淘汰`;
  byId("cache-default-summary").textContent = `${apiDefault} / ${imageDefault} 秒`;
  renderCacheTable("api");
  renderCacheTable("image");
}

function render() {
  renderTokenStats();
  renderServerOptions();
  renderSessionOptions();
  renderLegacyBilei();
  renderBindings();
  renderSubscriptions();
  renderAliases();
  renderKungfu();
  renderAccessControls();
  renderAccessEntries();
  renderAccessKeyOptions();
  renderAccessRecent();
  renderSummary();
  renderCache();
}

async function loadData() {
  const data = await bridge.apiGet("dashboard");
  Object.assign(state, data);
  render();
}

async function mutate(endpoint, payload, successMessage) {
  try {
    await bridge.apiPost(endpoint, payload);
    await loadData();
    showToast(successMessage);
    return true;
  } catch (error) {
    showToast(error?.message || "操作失败", true);
    return false;
  }
}

function resetRestoreConfirmation(control) {
  const timer = restoreConfirmationTimers.get(control);
  if (timer) clearTimeout(timer);
  restoreConfirmationTimers.delete(control);
  delete control.dataset.confirming;
  control.classList.remove("button--danger");
  control.textContent = "恢复默认";
}

function confirmRestoreInPage(control, confirmation) {
  if (control.dataset.confirming === "true") {
    resetRestoreConfirmation(control);
    return true;
  }

  control.dataset.confirming = "true";
  control.classList.add("button--danger");
  control.textContent = "再次点击确认";
  showToast(confirmation);
  restoreConfirmationTimers.set(
    control,
    setTimeout(() => resetRestoreConfirmation(control), 5000),
  );
  return false;
}

async function restoreDefaults(control, endpoint, confirmation, successMessage, resetEditing) {
  if (!confirmRestoreInPage(control, confirmation)) return;
  const originalLabel = control.textContent;
  control.disabled = true;
  control.textContent = "恢复中…";
  resetEditing();
  try {
    await bridge.apiPost(endpoint, {});
    await loadData();
    showToast(successMessage);
  } catch (error) {
    showToast(error?.message || "恢复默认失败", true);
  } finally {
    control.disabled = false;
    control.textContent = originalLabel;
  }
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => {
      const active = item === tab;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      const active = panel.id === `${tab.dataset.tab}-panel`;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  });
});

byId("add-subscription").addEventListener("click", () => openSubscriptionEditor());
byId("cancel-subscription").addEventListener("click", () => {
  byId("subscription-form").hidden = true;
  editing.subscriptionSession = null;
});
byId("subscription-events").addEventListener("change", updateSubscriptionSelectionCount);
byId("subscription-select-all").addEventListener("click", () => {
  byId("subscription-events").querySelectorAll("input").forEach((input) => { input.checked = true; });
  updateSubscriptionSelectionCount();
});
byId("subscription-clear-all").addEventListener("click", () => {
  byId("subscription-events").querySelectorAll("input").forEach((input) => { input.checked = false; });
  updateSubscriptionSelectionCount();
});
byId("subscription-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (subscriptionSaving) return;
  const form = event.currentTarget;
  const sessionId = (editing.subscriptionSession ?? byId("subscription-session").value).trim();
  if (!sessionId) {
    showToast("会话 ID 不能为空", true);
    byId("subscription-session").focus();
    return;
  }
  const payload = {
    session_id: sessionId,
    enabled: byId("subscription-enabled").checked,
    actions: [...byId("subscription-events").querySelectorAll("input:checked")].map((input) => Number(input.value)),
    mode: editing.subscriptionSession === null ? "create" : "update",
  };
  subscriptionSaving = true;
  byId("subscription-fields").disabled = true;
  byId("add-subscription").disabled = true;
  try {
    const saved = await mutate("subscriptions/save", payload, "会话推送配置已保存");
    if (saved) {
      form.hidden = true;
      editing.subscriptionSession = null;
    }
  } finally {
    subscriptionSaving = false;
    byId("subscription-fields").disabled = false;
    byId("add-subscription").disabled = false;
  }
});

byId("binding-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const saved = await mutate("bindings/save", {
    session_id: byId("binding-session").value,
    server: byId("binding-server").value,
  }, "绑定信息已保存");
  if (saved) event.currentTarget.reset();
});

byId("restore-aliases").addEventListener("click", async (event) => {
  await restoreDefaults(
    event.currentTarget,
    "aliases/restore",
    "再次点击按钮，确认使用内置 JSON 覆盖当前全部区服别名",
    "区服别名已恢复默认",
    () => { editing.aliasServer = null; },
  );
});

byId("restore-kungfu").addEventListener("click", async (event) => {
  await restoreDefaults(
    event.currentTarget,
    "kungfu/restore",
    "再次点击按钮，确认使用内置 JSON 覆盖当前全部心法及别名",
    "心法别名已恢复默认",
    () => { editing.kungfuPzid = null; },
  );
});

byId("api-cache-filter").addEventListener("input", () => renderCacheTable("api"));
byId("image-cache-filter").addEventListener("input", () => renderCacheTable("image"));

byId("cache-default-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    await bridge.apiPost("cache/settings/save", {
      cache_type: "api",
      cache_name: "*",
      ttl_seconds: Number(byId("api-default-ttl").value),
    });
    await bridge.apiPost("cache/settings/save", {
      cache_type: "image",
      cache_name: "*",
      ttl_seconds: Number(byId("image-default-ttl").value),
    });
    await loadData();
    showToast("默认缓存时间已保存");
  } catch (error) {
    showToast(error?.message || "默认缓存时间保存失败", true);
  } finally {
    submit.disabled = false;
  }
});

byId("cache-limit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    await bridge.apiPost("cache/limits/save", {
      api_memory_max_mb: Number(byId("api-memory-size-limit").value),
      api_max_entries: Number(byId("api-entry-limit").value),
      image_max_mb: Number(byId("image-size-limit").value),
    });
    await loadData();
    showToast("缓存容量限制已保存并立即生效");
  } catch (error) {
    showToast(error?.message || "缓存容量限制保存失败", true);
  } finally {
    submit.disabled = false;
  }
});

async function clearCache(cacheType, control) {
  control.disabled = true;
  try {
    const result = await bridge.apiPost("cache/clear", { cache_type: cacheType });
    await loadData();
    const removed = result?.removed?.[cacheType] ?? 0;
    showToast(`${cacheType === "api" ? "接口" : "图片"}缓存已清空，共清理 ${removed} 项`);
  } catch (error) {
    showToast(error?.message || "缓存清理失败", true);
  } finally {
    control.disabled = false;
  }
}

byId("clear-api-cache").addEventListener("click", (event) => {
  clearCache("api", event.currentTarget);
});
byId("clear-image-cache").addEventListener("click", (event) => {
  clearCache("image", event.currentTarget);
});

async function saveAccessConfig() {
  const checked = document.querySelector('input[name="access-mode"]:checked');
  const mode = checked ? checked.value : "all";
  return mutate("access/config", {
    mode,
    private_allowed: byId("access-private").checked,
    reply_on_deny: byId("access-reply").checked,
  }, "授权管理配置已保存");
}

document.querySelectorAll('input[name="access-mode"]').forEach((radio) => {
  radio.addEventListener("change", saveAccessConfig);
});
byId("access-private").addEventListener("change", saveAccessConfig);
byId("access-reply").addEventListener("change", saveAccessConfig);

byId("access-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const saved = await mutate("access/entries/add", {
    key: byId("access-key").value,
    note: byId("access-note").value,
  }, "名单条目已保存");
  if (saved) event.currentTarget.reset();
});

byId("refresh").addEventListener("click", async (event) => {
  const control = event.currentTarget;
  control.disabled = true;
  try {
    await loadData();
    showToast("页面数据已刷新");
  } catch (error) {
    showToast(error?.message || "刷新失败", true);
  } finally {
    control.disabled = false;
  }
});

await bridge.ready();
try {
  await loadData();
} catch (error) {
  showToast(error?.message || "管理数据加载失败", true);
}
