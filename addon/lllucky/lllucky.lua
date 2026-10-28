-- lllucky: in-game controls only. The companion changes the actual equipped bonuses.
local MAX_PERCENT = 1000000
local started = false
local channelOK = false
local elapsed = 0
local heartbeat = 0
local db

local panel = CreateFrame("Frame", "llluckyPanel", UIParent)
panel:SetWidth(390)
panel:SetHeight(270)
panel:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
panel:SetFrameStrata("DIALOG")
panel:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
  tile = true, tileSize = 16, edgeSize = 16, insets = { left = 4, right = 4, top = 4, bottom = 4 } })
panel:SetBackdropColor(0.035, 0.035, 0.05, 0.96)
panel:SetBackdropBorderColor(0.75, 0.61, 0.22, 1)
panel:SetMovable(true)
panel:EnableMouse(true)
panel:RegisterForDrag("LeftButton")
panel:SetScript("OnDragStart", function() this:StartMoving() end)
panel:SetScript("OnDragStop", function()
  this:StopMovingOrSizing()
  if db then
    local p, relative, rp, x, y = this:GetPoint()
    db.point = { p, rp, x, y }
  end
end)
panel:Hide()

local function Text(font, x, y, content)
  local label = panel:CreateFontString(nil, "OVERLAY", font)
  label:SetPoint("TOPLEFT", panel, "TOPLEFT", x, y)
  label:SetJustifyH("LEFT")
  label:SetText(content or "")
  return label
end

Text("GameFontNormalLarge", 20, -20, "lllucky · 幸运控制")
Text("GameFontHighlightSmall", 20, -46, "天选者印记 / 原始的附魔南海海带")
local close = CreateFrame("Button", nil, panel, "UIPanelCloseButton")
close:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -4, -4)
close:SetScript("OnClick", function() panel:Hide() if db then db.shown = false end end)

local enabled = CreateFrame("CheckButton", "llluckyEnabledButton", panel, "UICheckButtonTemplate")
enabled:SetWidth(26)
enabled:SetHeight(26)
enabled:SetPoint("TOPLEFT", panel, "TOPLEFT", 18, -67)
Text("GameFontHighlight", 49, -74, "启用幸运调整")
Text("GameFontNormal", 20, -112, "每件加成（%）")
local entry = CreateFrame("EditBox", "llluckyPercentInput", panel, "InputBoxTemplate")
entry:SetWidth(112)
entry:SetHeight(26)
entry:SetPoint("TOPLEFT", panel, "TOPLEFT", 155, -104)
entry:SetAutoFocus(false)
entry:SetNumeric(true)
entry:SetMaxLetters(7)

local status = Text("GameFontHighlightSmall", 20, -191, "")
status:SetWidth(350)
local actual = Text("GameFontNormal", 20, -215, "游戏实际总幸运：等待进入一局")
Text("GameFontDisableSmall", 20, -244, "两件同时装备会叠加；关闭开关恢复原加成")

local function Say(text)
  DEFAULT_CHAT_FRAME:AddMessage("|cffffcc33lllucky|r: " .. text)
end

local function CVar(name)
  if type(GetCVar) ~= "function" then return nil end
  local ok, value = pcall(GetCVar, name)
  if ok then return value end
  return nil
end

local function Write(name, value)
  if type(SetCVar) ~= "function" then return false end
  local ok = pcall(SetCVar, name, tostring(value))
  if not ok then return false end
  return tostring(CVar(name)) == tostring(value)
end

local function Beat()
  if channelOK then Write("llluckyBeat", math.floor(GetTime())) end
end

local function Publish()
  if not db then return end
  if not channelOK then
    status:SetText("|cffff5555当前客户端的设置通道不可用|r")
    return
  end
  local a = Write("llluckyEnabled", db.enabled and "1" or "0")
  local b = Write("llluckyPercent", string.format("%.0f", db.percent))
  if not a or not b then
    status:SetText("|cffff5555设置未写入，请检查客户端版本|r")
    return
  end
  Beat()
  status:SetText(db.enabled and "开关：开启 · 设置同步约需 1–2 秒" or "开关：关闭 · 正在恢复原加成")
end

local function Apply()
  if not db then return end
  local amount = tonumber(entry:GetText())
  if not amount or amount < 0 or amount > MAX_PERCENT then
    status:SetText("|cffff5555请输入 0–1000000 的百分比|r")
    return
  end
  db.percent = math.floor(amount)
  db.enabled = enabled:GetChecked() and true or false
  entry:ClearFocus()
  Publish()
end

local function Button(label, x, y, width, handler)
  local button = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
  button:SetWidth(width)
  button:SetHeight(24)
  button:SetPoint("TOPLEFT", panel, "TOPLEFT", x, y)
  button:SetText(label)
  button:SetScript("OnClick", handler)
  return button
end

Button("应用", 290, -105, 75, Apply)
local presets = { 300, 1000, 10000, 1000000 }
for index = 1, table.getn(presets) do
  local amount = presets[index]
  Button(tostring(amount) .. "%", 20 + (index - 1) * 89, -150, 82, function()
    entry:SetText(tostring(amount))
    Apply()
  end)
end
entry:SetScript("OnEnterPressed", Apply)
entry:SetScript("OnEscapePressed", function() this:ClearFocus() end)
enabled:SetScript("OnClick", function()
  if db then db.enabled = this:GetChecked() and true or false Publish() end
end)

local function Initialize()
  if started then return end
  started = true
  if type(llluckyDB) ~= "table" then llluckyDB = {} end
  db = llluckyDB
  if db.enabled == nil then db.enabled = true end
  if type(db.percent) ~= "number" or db.percent < 0 or db.percent > MAX_PERCENT then db.percent = 300 end
  if type(RegisterCVar) == "function" then
    pcall(RegisterCVar, "llluckySchema", "0")
    pcall(RegisterCVar, "llluckyEnabled", "0")
    pcall(RegisterCVar, "llluckyPercent", "0")
    pcall(RegisterCVar, "llluckyBeat", "0")
    channelOK = CVar("llluckySchema") ~= nil
  end
  if channelOK then
    if CVar("llluckySchema") == "1" then
      db.enabled = CVar("llluckyEnabled") == "1"
      local saved = tonumber(CVar("llluckyPercent"))
      if saved and saved >= 0 and saved <= MAX_PERCENT then db.percent = saved end
    end
    channelOK = Write("llluckySchema", "1")
  end
  enabled:SetChecked(db.enabled)
  entry:SetText(string.format("%.0f", db.percent))
  if type(db.point) == "table" then
    panel:ClearAllPoints()
    panel:SetPoint(db.point[1] or "CENTER", UIParent, db.point[2] or "CENTER", db.point[3] or 0, db.point[4] or 0)
  end
  if db.shown ~= false then panel:Show() end
  Publish()
  Say("已加载。输入 /lllucky 打开面板。")
end

local driver = CreateFrame("Frame")
driver:RegisterEvent("VARIABLES_LOADED")
driver:RegisterEvent("PLAYER_LOGIN")
driver:SetScript("OnEvent", Initialize)
driver:SetScript("OnUpdate", function()
  elapsed = elapsed + arg1
  heartbeat = heartbeat + arg1
  if not started then Initialize() end
  if heartbeat >= 4 then heartbeat = 0 Beat() end
  if elapsed < 0.5 then return end
  elapsed = 0
  local stats = AZS_STATS
  if type(stats) == "table" and tonumber(stats.luck) then
    actual:SetText("游戏实际总幸运：" .. string.format("%.0f", tonumber(stats.luck) * 100) .. "%")
  else
    actual:SetText("游戏实际总幸运：等待进入一局")
  end
end)

local function TogglePanel()
  if not started then Initialize() end
  if panel:IsShown() then panel:Hide() db.shown = false else panel:Show() db.shown = true end
end
SLASH_LLLUCKY1 = "/lllucky"
SLASH_LLLUCKY2 = "/luck"
SlashCmdList["LLLUCKY"] = function(message)
  if not started then Initialize() end
  local text = string.lower(message or "")
  if text == "on" or text == "off" then
    db.enabled = text == "on"
    enabled:SetChecked(db.enabled)
    Publish()
  elseif tonumber(text) then
    entry:SetText(text)
    Apply()
  else
    TogglePanel()
  end
end

if type(UISpecialFrames) == "table" then table.insert(UISpecialFrames, "llluckyPanel") end
local anchor = Minimap or UIParent
local minimapButton = CreateFrame("Button", "llluckyMinimapButton", anchor)
minimapButton:SetWidth(24)
minimapButton:SetHeight(24)
minimapButton:SetPoint("BOTTOMLEFT", anchor, "BOTTOMLEFT", 10, -4)
local icon = minimapButton:CreateTexture(nil, "ARTWORK")
icon:SetAllPoints(minimapButton)
icon:SetTexture("Interface\\Icons\\INV_Jewelry_Talisman_08")
minimapButton:SetScript("OnClick", TogglePanel)
minimapButton:SetScript("OnEnter", function()
  GameTooltip:SetOwner(this, "ANCHOR_LEFT")
  GameTooltip:AddLine("lllucky 幸运控制", 1, 0.8, 0.2)
  GameTooltip:AddLine("点击打开面板；命令 /lllucky", 1, 1, 1)
  GameTooltip:Show()
end)
minimapButton:SetScript("OnLeave", function() GameTooltip:Hide() end)
