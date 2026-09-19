/**
 * GOOGLE APPS SCRIPT CHO BOT TRADING CHỨNG KHOÁN VIỆT NAM (@NinhVNStock_bot)
 * Kết nối Google Sheets: https://docs.google.com/spreadsheets/d/1mjYsI-sXYgqAaebNXJb8BA4hwLZWxh-Cqji8p_F-dwo/edit
 * 
 * HƯỚNG DẪN CÀI ĐẶT NHANH (CHỈ MẤT 1 PHÚT):
 * 1. Mở file Google Sheet trên trình duyệt: 
 *    https://docs.google.com/spreadsheets/d/1mjYsI-sXYgqAaebNXJb8BA4hwLZWxh-Cqji8p_F-dwo/edit
 * 2. Trên thanh menu, bấm: Tiện ích mở rộng (Extensions) -> Apps Script.
 * 3. Xóa sạch mọi mã có sẵn, dán toàn bộ đoạn code này vào.
 * 4. Bấm "Triển khai" (Deploy) -> "Tùy chọn triển khai mới" (New deployment).
 *    - Chọn loại: Ứng dụng web (Web app) - hình bánh răng ⚙️
 *    - Thực thi dưới dạng (Execute as): "Tôi" (Me)
 *    - Ai có quyền truy cập (Who has access): "Bất kỳ ai" (Anyone)
 * 5. Bấm "Triển khai" (Deploy) -> Cấp quyền nếu Google hỏi -> Sao chép URL ứng dụng web (dạng https://script.google.com/macros/s/xxxx/exec).
 * 6. Dán URL vào file D:\MyAgent\.env:
 *    TRADING_WEBAPP_URL=https://script.google.com/macros/s/xxxx/exec
 */

function doGet(e) {
  return jsonResponse({ status: "ok", message: "VNStock Trading Bot Google Sheet API Ready" });
}

function doPost(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var postData = {};
  try {
    postData = JSON.parse(e.postData.contents);
  } catch (err) {
    return jsonResponse({ status: "error", message: "Invalid JSON: " + err.toString() });
  }

  var action = postData.action || "";

  // 1. ĐỒNG BỘ TOÀN BỘ BẢNG (Trading_Portfolio, Smart_Money_Alerts, ...)
  if (action === "sync_sheet") {
    var sheetName = postData.sheet_name || "Sheet1";
    var ws = getOrCreateSheet(ss, sheetName);
    var cols = postData.columns || [];
    var rows = postData.rows || [];

    ws.clearContents();
    if (cols.length > 0) {
      ws.getRange(1, 1, 1, cols.length).setValues([cols]);
      ws.getRange(1, 1, 1, cols.length).setFontWeight("bold").setBackground("#d2e3fc");
    }
    if (rows.length > 0) {
      ws.getRange(2, 1, rows.length, rows[0].length).setValues(rows);
    }
    return jsonResponse({ status: "success", synced_sheet: sheetName, count: rows.length });
  }

  // 2. GHI THÊM DÒNG MỚI (Trading_Orders - Nhật ký lệnh mua/bán)
  if (action === "append_row") {
    var sheetName = postData.sheet_name || "Trading_Orders";
    var ws = getOrCreateSheet(ss, sheetName);
    var cols = postData.columns || [];
    var row = postData.row || [];

    // Nếu sheet còn trống thì chèn tiêu đề cột
    if (ws.getLastRow() === 0 && cols.length > 0) {
      ws.getRange(1, 1, 1, cols.length).setValues([cols]);
      ws.getRange(1, 1, 1, cols.length).setFontWeight("bold").setBackground("#fce8e6");
    }

    if (row.length > 0) {
      ws.appendRow(row);
    }
    return jsonResponse({ status: "success", appended_to: sheetName });
  }

  return jsonResponse({ status: "ok" });
}

function getOrCreateSheet(ss, name) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
  }
  return sheet;
}

function jsonResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
