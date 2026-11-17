-- Fish Voiceover - DaVinci Resolve script (Workspace > Scripts > Fish Voiceover).
-- Free Resolve sandboxes Lua (no files, processes or HTTP), so the script talks to the
-- background helper fish_service.pyw: request = a FISHVO_REQ line in Resolve's log (printerr),
-- answer = a marker file in the queue folder, read with MediaStorage:GetFileList.
-- Then it imports the WAV and places it at the playhead on the first free audio track.
local QUEUE = os.getenv("USERPROFILE") .. "\\Documents\\FishVoiceoverResolve\\queue"
local BIN_NAME = "Fish Voiceover"
local WAIT_LIMIT = 3 * 3600

local function say(text)
  printerr("FISHVO_MSG\t" .. tostring(text):gsub("[\r\n]+", "\t"))
end

local function tc_to_frame(tc, fps)
  local h, m, s, f = tc:match("(%d+)[:;.](%d+)[:;.](%d+)[:;.](%d+)")
  h, m, s, f = tonumber(h), tonumber(m), tonumber(s), tonumber(f)
  local base = math.floor(fps + 0.5)
  local total = ((h * 60 + m) * 60 + s) * base + f
  if tc:find(";") and (base == 30 or base == 60) then
    local drop = base == 30 and 2 or 4
    local mins = h * 60 + m
    total = total - drop * (mins - math.floor(mins / 10))
  end
  return total
end

-- Names (without ".wav") of queue markers starting with prefix, prefix stripped.
local function markers(ms, prefix)
  local out = {}
  for _, p in ipairs(ms:GetFileList(QUEUE) or {}) do
    if type(p) == "string" then
      local name = p:match("([^\\/]+)$") or ""
      if name:sub(1, #prefix) == prefix then out[#out + 1] = name:sub(#prefix + 1, -5) end
    end
  end
  return out
end

local function has(list, value)
  for _, v in ipairs(list) do if v == value then return true end end
  return false
end

local function decode_path(s)
  return (s:gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end))
end

local function get_bin(mp)
  local root = mp:GetRootFolder()
  for _, sub in ipairs(root:GetSubFolderList() or {}) do
    if sub:GetName() == BIN_NAME then return sub end
  end
  return mp:AddSubFolder(root, BIN_NAME) or root
end

local function free_audio_track(tl, s, e)
  for i = 1, tl:GetTrackCount("audio") do
    if not tl:GetIsTrackLocked("audio", i) and tl:GetIsTrackEnabled("audio", i) ~= false then
      local busy = false
      for _, it in ipairs(tl:GetItemListInTrack("audio", i) or {}) do
        if it:GetStart() < e and it:GetEnd() > s then busy = true break end
      end
      if not busy then return i end
    end
  end
  tl:AddTrack("audio", "stereo")
  return tl:GetTrackCount("audio")
end

local function main()
  local proj = resolve:GetProjectManager():GetCurrentProject()
  local tl = proj and proj:GetCurrentTimeline()
  if not tl then return say("Open a timeline first.") end

  local fps = tonumber(tostring(tl:GetSetting("timelineFrameRate")):match("[%d.]+")) or 25
  local tc = tl:GetCurrentTimecode()
  local record = tc_to_frame(tc, fps)
  local ms = resolve:GetMediaStorage()

  local id = os.date("%Y%m%d%H%M%S") .. string.sub(bmd.createuuid(), 1, 6)
  printerr("FISHVO_REQ\t" .. id .. "\t" .. proj:GetName():gsub("[\t\r\n]", " ") .. "\t" .. tc)

  local started, acked, res = os.time(), false, {}
  while not has(res, "end") do
    wait(0.3)
    res = markers(ms, "res_" .. id .. "_")
    if has(res, "cancel") then return end
    acked = acked or #markers(ms, "ack_" .. id) > 0
    if not acked and os.time() - started > 8 then
      return print("Fish Voiceover: helper is not running - start fish_service.pyw (it autostarts with Windows).")
    end
    if os.time() - started > WAIT_LIMIT then return end
  end
  local parts = { p = {}, t = {} }
  for _, m in ipairs(res) do
    local kind, n, chunk = m:match("^([pt])(%d%d%d)_(.*)$")
    if kind then parts[kind][tonumber(n) + 1] = chunk end
  end
  local path = decode_path(table.concat(parts.p))
  local text = decode_path(table.concat(parts.t))
  local mp = proj:GetMediaPool()
  mp:SetCurrentFolder(get_bin(mp))
  local items = mp:ImportMedia({ path })
  local item = items and items[1]
  if not item then return say("Saved, but Resolve could not import:\n" .. path) end

  -- Audio clips report Duration at the clip's FPS; Frames is often empty.
  local clip_fps = tonumber(tostring(item:GetClipProperty("FPS")):match("[%d.]+")) or fps
  local frames = tonumber(item:GetClipProperty("Frames") or "")
  if not frames or frames < 1 then
    local dur = tostring(item:GetClipProperty("Duration"))
    frames = tc_to_frame(dur:find("%d+[:;.]%d+[:;.]%d+[:;.]%d+") and dur or "00:00:00:01", clip_fps)
  end
  if frames < 1 then frames = 1 end
  local span = math.ceil(frames * fps / clip_fps)
  local track = free_audio_track(tl, record, record + span)
  local placed = mp:AppendToTimeline({ {
    mediaPoolItem = item, startFrame = 0, endFrame = frames - 1,
    mediaType = 2, trackIndex = track, recordFrame = record,
  } })
  if not placed or not placed[1] then
    return say("Saved and imported into the '" .. BIN_NAME .. "' bin, but could not place it on the timeline:\n" .. path)
  end
  -- Voiced text as a marker on the clip: name = start of the phrase, note = full text.
  if text ~= "" then
    local title = text:gsub("%s+", " ")
    if #title > 60 then title = title:sub(1, 60):gsub("[\128-\191]*$", ""):gsub("[\192-\255]$", "") .. "…" end
    placed[1]:AddMarker(0, "Blue", title, text, 1)
  end
  tl:SetCurrentTimecode(tc)
end

local ok, err = pcall(main)
if not ok then say("Script error: " .. tostring(err)) end
