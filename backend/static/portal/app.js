(function () {
  "use strict";

  var DEMO_EMAIL = "demo@acme.com";
  var DEMO_PASSWORD = "demo1234";
  var RECAPTCHA_CONFIG_URL = "/api/test/recaptcha-config";
  var RECAPTCHA_VERIFY_URL = "/api/test/recaptcha-verify";
  var _recaptchaWidgetRendered = false;
  var _recaptchaApiReady = false;

  var I18N = {
    zh: {
      brand: "Acme Supply Hub",
      brand_sub: "B2B 供应商协作门户 · Supplier Portal",
      email: "邮箱 Email",
      password: "密码 Password",
      continue: "继续 Continue",
      recaptcha_hint: "请完成 reCAPTCHA 人机验证",
      verify: "验证 Verify",
      back: "返回 Back",
      portal: "供应商门户",
      nav_dashboard: "仪表盘",
      nav_orders: "采购订单",
      nav_shipments: "物流追踪",
      nav_invoices: "发票对账",
      nav_support: "技术支持",
      logout: "退出 Logout",
      kpi_open: "待处理订单",
      kpi_transit: "在途发货",
      kpi_invoices: "待对账发票",
      kpi_fulfillment: "准时交付率",
      recent_orders: "最近订单",
      view_all: "查看全部",
      col_order_id: "订单号",
      col_buyer: "采购方",
      col_amount: "金额",
      col_status: "状态",
      col_items: "行项",
      col_date: "下单日期",
      col_invoice_id: "发票号",
      col_period: "账期",
      col_action: "操作",
      filter_orders: "筛选订单",
      all_status: "全部",
      status_confirmed: "已确认",
      status_processing: "处理中",
      status_shipped: "已发货",
      status_delivered: "已交付",
      date_from: "起始日期",
      search: "搜索 Search",
      order_list: "订单列表",
      order_detail: "订单详情",
      select_order: "点击左侧订单行查看详情",
      role_info: "当前角色: 供应商管理员 — 可审批加急订单",
      approve_rush: "批准加急",
      shipment_tracking: "物流追踪",
      invoice_list: "发票列表",
      invoice_summary: "发票摘要",
      download_summary: "下载摘要",
      support_ticket: "提交工单",
      wiz_category: "1. 选择类别",
      wiz_details: "2. 填写详情",
      wiz_confirm: "3. 确认提交",
      ticket_category: "问题类别",
      select_category: "请选择...",
      cat_delivery: "物流配送",
      cat_quality: "产品质量",
      cat_billing: "账单对账",
      cat_integration: "系统对接",
      next: "下一步 Next",
      ticket_subject: "主题",
      ticket_description: "详细描述",
      submit_ticket: "提交工单",
      ticket_created: "工单已创建",
      invalid_credentials: "邮箱或密码不正确",
      invalid_recaptcha: "请完成 reCAPTCHA 验证",
      recaptcha_verify_failed: "reCAPTCHA 验证失败，请重试",
      orders_found: "条订单",
      expand_tracking: "展开追踪",
      collapse_tracking: "收起追踪",
      line_items: "行项目",
      total: "合计",
      approved_rush: "加急订单已批准",
    },
    en: {
      brand: "Acme Supply Hub",
      brand_sub: "B2B Supplier Collaboration Portal",
      email: "Email",
      password: "Password",
      continue: "Continue",
      recaptcha_hint: "Complete the reCAPTCHA checkbox to continue",
      verify: "Verify",
      back: "Back",
      portal: "Supplier Portal",
      nav_dashboard: "Dashboard",
      nav_orders: "Orders",
      nav_shipments: "Shipments",
      nav_invoices: "Invoices",
      nav_support: "Support",
      logout: "Logout",
      kpi_open: "Open Orders",
      kpi_transit: "In Transit",
      kpi_invoices: "Pending Invoices",
      kpi_fulfillment: "On-time Rate",
      recent_orders: "Recent Orders",
      view_all: "View All",
      col_order_id: "Order ID",
      col_buyer: "Buyer",
      col_amount: "Amount",
      col_status: "Status",
      col_items: "Items",
      col_date: "Order Date",
      col_invoice_id: "Invoice ID",
      col_period: "Period",
      col_action: "Action",
      filter_orders: "Filter Orders",
      all_status: "All",
      status_confirmed: "Confirmed",
      status_processing: "Processing",
      status_shipped: "Shipped",
      status_delivered: "Delivered",
      date_from: "From Date",
      search: "Search",
      order_list: "Order List",
      order_detail: "Order Detail",
      select_order: "Click a row to view details",
      role_info: "Role: Supplier Admin — can approve rush orders",
      approve_rush: "Approve Rush",
      shipment_tracking: "Shipment Tracking",
      invoice_list: "Invoice List",
      invoice_summary: "Invoice Summary",
      download_summary: "Download Summary",
      support_ticket: "Submit Ticket",
      wiz_category: "1. Category",
      wiz_details: "2. Details",
      wiz_confirm: "3. Confirm",
      ticket_category: "Category",
      select_category: "Select...",
      cat_delivery: "Delivery & Logistics",
      cat_quality: "Product Quality",
      cat_billing: "Billing & Reconciliation",
      cat_integration: "System Integration",
      next: "Next",
      ticket_subject: "Subject",
      ticket_description: "Description",
      submit_ticket: "Submit Ticket",
      ticket_created: "Ticket Created",
      invalid_credentials: "Invalid email or password",
      invalid_recaptcha: "Please complete the reCAPTCHA checkbox",
      recaptcha_verify_failed: "reCAPTCHA verification failed, please try again",
      orders_found: "orders",
      expand_tracking: "Expand tracking",
      collapse_tracking: "Collapse tracking",
      line_items: "Line Items",
      total: "Total",
      approved_rush: "Rush order approved",
    },
  };

  var ORDERS = [
    {
      id: "PO-2024-8842",
      buyer: "华东精密制造有限公司",
      buyerEn: "East China Precision Mfg.",
      items: 4,
      amount: 128450.0,
      status: "processing",
      date: "2024-11-18",
      rush: true,
      lineItems: [
        { sku: "BRG-6205-2RS", name: "深沟球轴承 6205-2RS", qty: 500, unitPrice: 12.5 },
        { sku: "SLV-M8-50", name: "不锈钢螺栓 M8×50", qty: 2000, unitPrice: 0.85 },
        { sku: "GSK-NBR-40", name: "NBR 密封垫圈 Φ40", qty: 800, unitPrice: 2.2 },
        { sku: "LUB-Grease-A", name: "工业润滑脂 1kg", qty: 120, unitPrice: 45.0 },
      ],
    },
    {
      id: "PO-2024-9103",
      buyer: "深圳智联科技",
      buyerEn: "Shenzhen SmartLink Tech",
      items: 2,
      amount: 67320.0,
      status: "shipped",
      date: "2024-11-22",
      rush: false,
      lineItems: [
        { sku: "PCB-Rev3-A", name: "主控板 PCB Rev3", qty: 300, unitPrice: 185.0 },
        { sku: "CONN-USB-C-12", name: "USB-C 连接器 12P", qty: 600, unitPrice: 19.7 },
      ],
    },
    {
      id: "PO-2024-9156",
      buyer: "北京云途物流",
      buyerEn: "Beijing Yuntu Logistics",
      items: 3,
      amount: 45200.0,
      status: "confirmed",
      date: "2024-11-25",
      rush: false,
      lineItems: [
        { sku: "TIRE-295-80R22", name: "卡车轮胎 295/80R22.5", qty: 40, unitPrice: 980.0 },
        { sku: "BRK-PAD-HD", name: "重型刹车片组", qty: 80, unitPrice: 125.0 },
        { sku: "FLT-AIR-HD01", name: "空气滤芯 HD-01", qty: 100, unitPrice: 35.0 },
      ],
    },
    {
      id: "PO-2024-9201",
      buyer: "广州南粤食品",
      buyerEn: "Guangzhou Nanyue Foods",
      items: 5,
      amount: 89300.0,
      status: "delivered",
      date: "2024-10-30",
      rush: false,
      lineItems: [
        { sku: "PKG-BOX-500", name: "瓦楞纸箱 500×400", qty: 5000, unitPrice: 3.2 },
        { sku: "LBL-Food-A", name: "食品标签 A 型", qty: 10000, unitPrice: 0.15 },
        { sku: "FLM-PE-30", name: "PE 保鲜膜 30cm", qty: 200, unitPrice: 28.0 },
        { sku: "TAPE-48-100", name: "封箱胶带 48mm", qty: 500, unitPrice: 4.5 },
        { sku: "PAL-STD-120", name: "标准托盘 120×100", qty: 50, unitPrice: 85.0 },
      ],
    },
    {
      id: "PO-2024-9228",
      buyer: "成都西部能源",
      buyerEn: "Chengdu West Energy",
      items: 2,
      amount: 215600.0,
      status: "processing",
      date: "2024-11-28",
      rush: true,
      lineItems: [
        { sku: "VLV-Gate-6in", name: "闸阀 DN150 6\"", qty: 24, unitPrice: 4200.0 },
        { sku: "FLG-Weld-150", name: "对焊法兰 DN150", qty: 48, unitPrice: 680.0 },
      ],
    },
  ];

  var SHIPMENTS = [
    {
      id: "SHP-2024-4412",
      orderId: "PO-2024-9103",
      carrier: "顺丰速运 SF Express",
      status: "in_transit",
      eta: "2024-12-02",
      events: [
        { time: "2024-11-28 09:15", desc: "快件已到达【深圳集散中心】", done: true },
        { time: "2024-11-28 14:30", desc: "快件离开【深圳集散中心】，下一站【武汉中转场】", done: true },
        { time: "2024-11-29 08:00", desc: "快件到达【武汉中转场】", done: true },
        { time: "2024-11-29 16:45", desc: "快件离开【武汉中转场】，下一站【北京顺义集散】", done: false },
        { time: "预计 2024-12-02", desc: "预计送达【北京云途物流仓库】", done: false },
      ],
    },
    {
      id: "SHP-2024-4388",
      orderId: "PO-2024-8842",
      carrier: "德邦物流 Deppon",
      status: "picked_up",
      eta: "2024-12-05",
      events: [
        { time: "2024-11-27 11:00", desc: "供应商仓库已揽收", done: true },
        { time: "2024-11-27 18:20", desc: "到达【上海枢纽中心】", done: true },
        { time: "2024-11-28 07:30", desc: "分拣中，等待干线发车", done: false },
      ],
    },
    {
      id: "SHP-2024-4355",
      orderId: "PO-2024-9201",
      carrier: "京东物流 JD Logistics",
      status: "delivered",
      eta: "2024-11-05",
      events: [
        { time: "2024-11-01 10:00", desc: "已揽收", done: true },
        { time: "2024-11-02 15:00", desc: "到达【广州分拣中心】", done: true },
        { time: "2024-11-04 09:30", desc: "派送中", done: true },
        { time: "2024-11-05 14:22", desc: "已签收 — 签收人: 仓库管理员 李工", done: true },
      ],
    },
  ];

  var INVOICES = [
    {
      id: "INV-2024-3301",
      orderId: "PO-2024-9201",
      period: "2024-Q4",
      amount: 89300.0,
      status: "paid",
      buyer: "广州南粤食品",
      taxRate: 0.13,
      dueDate: "2024-11-15",
      lineItems: [
        { desc: "包装材料套装", amount: 89300.0 },
      ],
    },
    {
      id: "INV-2024-3318",
      orderId: "PO-2024-9103",
      period: "2024-Q4",
      amount: 67320.0,
      status: "pending",
      buyer: "深圳智联科技",
      taxRate: 0.13,
      dueDate: "2024-12-15",
      lineItems: [
        { desc: "PCB 及连接器", amount: 67320.0 },
      ],
    },
    {
      id: "INV-2024-3325",
      orderId: "PO-2024-8842",
      period: "2024-Q4",
      amount: 128450.0,
      status: "pending",
      buyer: "华东精密制造有限公司",
      taxRate: 0.13,
      dueDate: "2024-12-20",
      lineItems: [
        { desc: "轴承及紧固件", amount: 98500.0 },
        { desc: "密封件及润滑脂", amount: 29950.0 },
      ],
    },
  ];

  var state = {
    lang: "en",
    page: "dashboard",
    authenticated: false,
    selectedOrderId: null,
    filteredOrders: ORDERS.slice(),
    supportDraft: {},
  };

  function t(key) {
    return (I18N[state.lang] && I18N[state.lang][key]) || key;
  }

  function applyI18n() {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
  }

  function statusBadge(status) {
    var map = {
      confirmed: ["badge-info", "status_confirmed"],
      processing: ["badge-warning", "status_processing"],
      shipped: ["badge-info", "status_shipped"],
      delivered: ["badge-success", "status_delivered"],
      in_transit: ["badge-info", "status_shipped"],
      picked_up: ["badge-warning", "status_processing"],
      paid: ["badge-success", "status_delivered"],
      pending: ["badge-warning", "status_processing"],
    };
    var pair = map[status] || ["badge-neutral", status];
    return '<span class="badge ' + pair[0] + '" data-status="' + status + '">' + t(pair[1]) + "</span>";
  }

  function formatCurrency(n) {
    return "¥" + n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function buyerName(order) {
    return state.lang === "zh" ? order.buyer : order.buyerEn;
  }

  function showLoginStep(step) {
    document.getElementById("login-form").classList.toggle("hidden", step !== 1);
    document.getElementById("recaptcha-form").classList.toggle("hidden", step !== 2);
    document.getElementById("step-dot-1").classList.toggle("active", step >= 1);
    document.getElementById("step-dot-2").classList.toggle("active", step >= 2);
    if (step === 2) {
      ensureRecaptchaWidget();
    }
  }

  function ensureRecaptchaWidget() {
    if (_recaptchaWidgetRendered || typeof grecaptcha === "undefined") return;
    fetch(RECAPTCHA_CONFIG_URL)
      .then(function (r) {
        return r.json();
      })
      .then(function (cfg) {
        if (_recaptchaWidgetRendered) return;
        grecaptcha.render("recaptcha-widget", {
          sitekey: cfg.site_key,
          callback: function () {
            var errEl = document.getElementById("recaptcha-error");
            if (errEl) errEl.classList.add("hidden");
          },
          "expired-callback": function () {
            var errEl = document.getElementById("recaptcha-error");
            if (errEl) {
              errEl.textContent = t("recaptcha_verify_failed");
              errEl.classList.remove("hidden");
            }
          },
        });
        _recaptchaWidgetRendered = true;
      })
      .catch(function () {
        var errEl = document.getElementById("recaptcha-error");
        if (errEl) {
          errEl.textContent = t("recaptcha_verify_failed");
          errEl.classList.remove("hidden");
        }
      });
  }

  window.onRecaptchaLoad = function () {
    _recaptchaApiReady = true;
    var form = document.getElementById("recaptcha-form");
    if (form && !form.classList.contains("hidden")) {
      ensureRecaptchaWidget();
    }
  };

  function showView(view) {
    document.getElementById("login-view").classList.toggle("hidden", view !== "login");
    document.getElementById("app-view").classList.toggle("hidden", view !== "app");
  }

  function navigate(page) {
    state.page = page;
    document.querySelectorAll(".page").forEach(function (p) {
      p.classList.add("hidden");
    });
    var el = document.getElementById("page-" + page);
    if (el) el.classList.remove("hidden");

    document.querySelectorAll(".nav-link").forEach(function (link) {
      link.classList.toggle("active", link.getAttribute("data-page") === page);
    });

    var titleKeys = {
      dashboard: "nav_dashboard",
      orders: "nav_orders",
      shipments: "nav_shipments",
      invoices: "nav_invoices",
      support: "nav_support",
    };
    document.getElementById("page-title").textContent = t(titleKeys[page] || page);
    document.getElementById("page-title").setAttribute("data-i18n", titleKeys[page] || page);

    if (page === "orders") renderOrdersTable();
    if (page === "shipments") renderShipments();
    if (page === "invoices") renderInvoices();
  }

  function renderDashboardOrders() {
    var tbody = document.getElementById("dashboard-orders-body");
    tbody.innerHTML = ORDERS.slice(0, 4)
      .map(function (o) {
        return (
          '<tr data-order-id="' +
          o.id +
          '" data-testid="dash-order-row-' +
          o.id +
          '">' +
          "<td>" +
          o.id +
          "</td>" +
          "<td>" +
          buyerName(o) +
          "</td>" +
          "<td>" +
          formatCurrency(o.amount) +
          "</td>" +
          "<td>" +
          statusBadge(o.status) +
          "</td></tr>"
        );
      })
      .join("");
  }

  function renderOrdersTable() {
    var tbody = document.getElementById("orders-table-body");
    tbody.innerHTML = state.filteredOrders
      .map(function (o, idx) {
        var selected = o.id === state.selectedOrderId ? " selected" : "";
        return (
          '<tr class="order-row' +
          selected +
          '" role="button" tabindex="0" aria-label="Order ' +
          o.id +
          '" data-order-id="' +
          o.id +
          '" data-row-index="' +
          idx +
          '" data-testid="order-row-' +
          o.id +
          '">' +
          "<td><strong>" +
          o.id +
          "</strong></td>" +
          "<td>" +
          buyerName(o) +
          "</td>" +
          "<td>" +
          o.items +
          "</td>" +
          "<td>" +
          formatCurrency(o.amount) +
          "</td>" +
          "<td>" +
          statusBadge(o.status) +
          "</td>" +
          "<td>" +
          o.date +
          "</td></tr>"
        );
      })
      .join("");

    document.getElementById("orders-count").textContent =
      state.filteredOrders.length + " " + t("orders_found");
  }

  function renderOrderDetail(order) {
    var panel = document.getElementById("order-detail-panel");
    if (!order) {
      panel.innerHTML =
        '<h4 data-i18n="order_detail">' +
        t("order_detail") +
        '</h4><p style="color:var(--muted);font-size:0.85rem">' +
        t("select_order") +
        "</p>";
      document.getElementById("approve-rush-btn").classList.add("hidden");
      return;
    }

    var lineRows = order.lineItems
      .map(function (li) {
        return (
          "<tr><td>" +
          li.sku +
          "</td><td>" +
          li.name +
          "</td><td>" +
          li.qty +
          "</td><td>" +
          formatCurrency(li.unitPrice) +
          "</td><td>" +
          formatCurrency(li.qty * li.unitPrice) +
          "</td></tr>"
        );
      })
      .join("");

    var extractData = {
      orderId: order.id,
      buyer: order.buyer,
      buyerEn: order.buyerEn,
      status: order.status,
      amount: order.amount,
      currency: "CNY",
      date: order.date,
      rush: order.rush,
      lineItems: order.lineItems,
    };

    panel.innerHTML =
      "<h4>" +
      order.id +
      "</h4>" +
      '<div class="detail-row"><span class="key">' +
      t("col_buyer") +
      '</span><span>' +
      buyerName(order) +
      "</span></div>" +
      '<div class="detail-row"><span class="key">' +
      t("col_status") +
      "</span><span>" +
      statusBadge(order.status) +
      "</span></div>" +
      '<div class="detail-row"><span class="key">' +
      t("col_date") +
      '</span><span>' +
      order.date +
      "</span></div>" +
      '<div class="detail-row"><span class="key">' +
      t("total") +
      '</span><span><strong>' +
      formatCurrency(order.amount) +
      "</strong></span></div>" +
      "<h4 style=\"margin-top:16px\">" +
      t("line_items") +
      "</h4>" +
      '<table class="line-items-table"><thead><tr><th>SKU</th><th>' +
      (state.lang === "zh" ? "名称" : "Name") +
      "</th><th>" +
      (state.lang === "zh" ? "数量" : "Qty") +
      "</th><th>" +
      (state.lang === "zh" ? "单价" : "Unit") +
      "</th><th>" +
      (state.lang === "zh" ? "小计" : "Subtotal") +
      "</th></tr></thead><tbody>" +
      lineRows +
      "</tbody></table>" +
      '<pre class="extract-json" id="order-json" data-testid="order-json">' +
      JSON.stringify(extractData, null, 2) +
      "</pre>";

    panel.setAttribute("data-order-id", order.id);
    panel.setAttribute("data-extract", JSON.stringify(extractData));

    var approveBtn = document.getElementById("approve-rush-btn");
    if (order.rush && order.status === "processing") {
      approveBtn.classList.remove("hidden");
      approveBtn.onclick = function () {
        order.rush = false;
        approveBtn.classList.add("hidden");
        alert(t("approved_rush"));
        renderOrderDetail(order);
      };
    } else {
      approveBtn.classList.add("hidden");
    }
  }

  function filterOrders() {
    var idFilter = document.getElementById("filter-order-id").value.trim().toLowerCase();
    var statusFilter = document.getElementById("filter-status").value;
    var dateFrom = document.getElementById("filter-date-from").value;

    state.filteredOrders = ORDERS.filter(function (o) {
      if (idFilter && o.id.toLowerCase().indexOf(idFilter) === -1) return false;
      if (statusFilter && o.status !== statusFilter) return false;
      if (dateFrom && o.date < dateFrom) return false;
      return true;
    });
    renderOrdersTable();
  }

  function renderShipments() {
    var container = document.getElementById("shipments-list");
    container.innerHTML = SHIPMENTS.map(function (s, idx) {
      var eventsHtml = s.events
        .map(function (ev) {
          return (
            '<div class="timeline-event" data-testid="timeline-event-' +
            idx +
            '">' +
            '<div class="timeline-dot' +
            (ev.done ? "" : " pending") +
            '"></div>' +
            '<div class="timeline-content">' +
            '<div class="time">' +
            ev.time +
            "</div>" +
            '<div class="desc">' +
            ev.desc +
            "</div></div></div>"
          );
        })
        .join("");

      return (
        '<div class="shipment-card" data-shipment-id="' +
        s.id +
        '" data-testid="shipment-card-' +
        s.id +
        '">' +
        '<div class="shipment-header" data-testid="shipment-toggle-' +
        s.id +
        '" role="button" tabindex="0" aria-expanded="false">' +
        '<div class="shipment-meta">' +
        "<strong>" +
        s.id +
        "</strong>" +
        "<span>" +
        s.carrier +
        "</span>" +
        statusBadge(s.status) +
        "</div>" +
        '<span data-i18n="expand_tracking">' +
        t("expand_tracking") +
        " ▼</span></div>" +
        '<div class="timeline hidden" data-testid="shipment-timeline-' +
        s.id +
        '">' +
        eventsHtml +
        "</div></div>"
      );
    }).join("");
  }

  function renderInvoices() {
    var tbody = document.getElementById("invoices-table-body");
    tbody.innerHTML = INVOICES.map(function (inv) {
      return (
        "<tr data-invoice-id=\"" +
        inv.id +
        "\" data-testid=\"invoice-row-" +
        inv.id +
        "\">" +
        "<td><strong>" +
        inv.id +
        "</strong></td>" +
        "<td>" +
        inv.orderId +
        "</td>" +
        "<td>" +
        inv.period +
        "</td>" +
        "<td>" +
        formatCurrency(inv.amount) +
        "</td>" +
        "<td>" +
        statusBadge(inv.status) +
        "</td>" +
        '<td><button class="btn btn-outline btn-sm download-summary-btn" data-invoice-id="' +
        inv.id +
        '" aria-label="Download Summary ' +
        inv.id +
        '" data-testid="download-summary-' +
        inv.id +
        '">' +
        t("download_summary") +
        "</button></td></tr>"
      );
    }).join("");

    // Restore Download Summary buttons when invoices page is re-rendered
    document.querySelectorAll(".download-summary-btn").forEach(function (btn) {
      btn.removeAttribute("aria-hidden");
      btn.setAttribute("tabindex", "0");
    });

    // Also hide the invoice panel
    var panel = document.getElementById("invoice-summary-panel");
    if (panel) panel.classList.add("hidden-panel");
  }

  function showInvoiceSummary(invoiceId) {
    var inv = INVOICES.find(function (i) {
      return i.id === invoiceId;
    });
    if (!inv) return;

    var taxAmount = inv.amount * inv.taxRate;
    var totalWithTax = inv.amount + taxAmount;
    var extractData = {
      invoiceId: inv.id,
      orderId: inv.orderId,
      buyer: inv.buyer,
      period: inv.period,
      status: inv.status,
      subtotal: inv.amount,
      taxRate: inv.taxRate,
      taxAmount: Math.round(taxAmount * 100) / 100,
      totalWithTax: Math.round(totalWithTax * 100) / 100,
      currency: "CNY",
      dueDate: inv.dueDate,
      lineItems: inv.lineItems,
    };

    var panel = document.getElementById("invoice-summary-panel");
    panel.classList.remove("hidden-panel");
    document.getElementById("invoice-summary-content").innerHTML =
      '<div class="detail-row"><span class="key">' +
      t("col_invoice_id") +
      "</span><span>" +
      inv.id +
      "</span></div>" +
      '<div class="detail-row"><span class="key">' +
      t("col_buyer") +
      "</span><span>" +
      inv.buyer +
      "</span></div>" +
      '<div class="detail-row"><span class="key">' +
      t("col_amount") +
      "</span><span>" +
      formatCurrency(inv.amount) +
      "</span></div>" +
      '<div class="detail-row"><span class="key">' +
      (state.lang === "zh" ? "税额 (13%)" : "Tax (13%)") +
      "</span><span>" +
      formatCurrency(taxAmount) +
      "</span></div>" +
      '<div class="detail-row"><span class="key">' +
      (state.lang === "zh" ? "含税合计" : "Total incl. tax") +
      "</span><span><strong>" +
      formatCurrency(totalWithTax) +
      "</strong></span></div>";

    document.getElementById("invoice-json").textContent = JSON.stringify(extractData, null, 2);
    panel.setAttribute("data-invoice-id", inv.id);
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });

    // Hide all Download Summary buttons from the accessibility tree while the panel is showing.
    // This ensures the agent sees only the "Invoice data ready" signal button and must call extract().
    document.querySelectorAll(".download-summary-btn").forEach(function (btn) {
      btn.setAttribute("aria-hidden", "true");
      btn.setAttribute("tabindex", "-1");
    });
  }

  function resetSupportWizard() {
    document.getElementById("support-step-1").classList.remove("hidden");
    document.getElementById("support-step-2").classList.add("hidden");
    document.getElementById("support-step-3").classList.add("hidden");
    document.getElementById("support-success").classList.add("hidden");
    ["wiz-step-1", "wiz-step-2", "wiz-step-3"].forEach(function (id, i) {
      var el = document.getElementById(id);
      el.classList.remove("active", "done");
      if (i === 0) el.classList.add("active");
    });
    state.supportDraft = {};
  }

  function setWizardStep(step) {
    document.getElementById("support-step-1").classList.toggle("hidden", step !== 1);
    document.getElementById("support-step-2").classList.toggle("hidden", step !== 2);
    document.getElementById("support-step-3").classList.toggle("hidden", step !== 3);
    ["wiz-step-1", "wiz-step-2", "wiz-step-3"].forEach(function (id, i) {
      var el = document.getElementById(id);
      el.classList.remove("active", "done");
      if (i + 1 < step) el.classList.add("done");
      else if (i + 1 === step) el.classList.add("active");
    });
  }

  function login() {
    state.authenticated = true;
    sessionStorage.setItem("acme_auth", "1");
    sessionStorage.setItem("acme_email", DEMO_EMAIL);
    showView("app");
    renderDashboardOrders();
    navigate("dashboard");
  }

  function logout() {
    state.authenticated = false;
    sessionStorage.removeItem("acme_auth");
    sessionStorage.removeItem("acme_email");
    showView("login");
    showLoginStep(1);
    document.getElementById("login-email").value = "";
    document.getElementById("login-password").value = "";
    if (_recaptchaWidgetRendered && typeof grecaptcha !== "undefined") {
      try {
        grecaptcha.reset();
      } catch (_e) {
        /* ignore */
      }
    }
  }

  var _loginAutoSubmitPending = false;

  function _doLoginCheck() {
    var email = document.getElementById("login-email").value.trim();
    var password = document.getElementById("login-password").value.trim();
    var errEl = document.getElementById("login-error");
    var loginForm = document.getElementById("login-form");
    if (!loginForm || loginForm.classList.contains("hidden")) return;
    if (email === DEMO_EMAIL && password === DEMO_PASSWORD) {
      errEl.classList.add("hidden");
      showLoginStep(2);
    }
  }

  function updateLoginSubmitState() {
    var email = document.getElementById("login-email").value.trim();
    var password = document.getElementById("login-password").value.trim();
    var btn = document.getElementById("login-submit-btn");
    if (btn) {
      if (email && password) {
        btn.textContent = "✓ Continue";
        btn.setAttribute("data-ready", "true");
        if (email === DEMO_EMAIL && password === DEMO_PASSWORD && !_loginAutoSubmitPending) {
          _loginAutoSubmitPending = true;
          _doLoginCheck();
          _loginAutoSubmitPending = false;
        }
      } else if (password && !email) {
        btn.textContent = "Enter email above";
        btn.setAttribute("data-ready", "partial");
      } else if (email && !password) {
        btn.textContent = "Enter password above";
        btn.setAttribute("data-ready", "partial");
      } else {
        btn.textContent = "Continue";
        btn.setAttribute("data-ready", "false");
      }
    }
  }

  function initEvents() {
    var emailInput = document.getElementById("login-email");
    var passwordInput = document.getElementById("login-password");
    if (emailInput) emailInput.addEventListener("input", updateLoginSubmitState);
    if (passwordInput) passwordInput.addEventListener("input", updateLoginSubmitState);

    document.getElementById("login-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var email = document.getElementById("login-email").value.trim();
      var password = document.getElementById("login-password").value;
      var errEl = document.getElementById("login-error");
      if (email === DEMO_EMAIL && password === DEMO_PASSWORD) {
        errEl.classList.add("hidden");
        showLoginStep(2);
      } else {
        errEl.textContent = t("invalid_credentials");
        errEl.classList.remove("hidden");
      }
    });

    document.getElementById("recaptcha-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var errEl = document.getElementById("recaptcha-error");
      if (!_recaptchaWidgetRendered || typeof grecaptcha === "undefined") {
        errEl.textContent = t("recaptcha_verify_failed");
        errEl.classList.remove("hidden");
        return;
      }
      var token = grecaptcha.getResponse();
      if (!token) {
        errEl.textContent = t("invalid_recaptcha");
        errEl.classList.remove("hidden");
        return;
      }
      var body = new FormData();
      body.set("g-recaptcha-response", token);
      var verifyBtn = document.querySelector("[data-testid=recaptcha-verify]");
      if (verifyBtn) verifyBtn.disabled = true;
      fetch(RECAPTCHA_VERIFY_URL, { method: "POST", body: body })
        .then(function (resp) {
          return resp.json().then(function (data) {
            return { ok: resp.ok, data: data };
          });
        })
        .then(function (result) {
          if (!result.ok || !result.data.success) {
            errEl.textContent = t("recaptcha_verify_failed");
            errEl.classList.remove("hidden");
            grecaptcha.reset();
            if (verifyBtn) verifyBtn.disabled = false;
            return;
          }
          errEl.classList.add("hidden");
          login();
        })
        .catch(function () {
          errEl.textContent = t("recaptcha_verify_failed");
          errEl.classList.remove("hidden");
          if (verifyBtn) verifyBtn.disabled = false;
        });
    });

    document.getElementById("recaptcha-back").addEventListener("click", function () {
      showLoginStep(1);
    });

    document.getElementById("logout-btn").addEventListener("click", logout);

    document.querySelectorAll(".nav-link").forEach(function (link) {
      link.addEventListener("click", function () {
        navigate(link.getAttribute("data-page"));
      });
    });

    document.getElementById("dash-goto-orders").addEventListener("click", function () {
      navigate("orders");
    });

    document.getElementById("dashboard-orders-body").addEventListener("click", function (e) {
      var row = e.target.closest("tr[data-order-id]");
      if (!row) return;
      navigate("orders");
      selectOrder(row.getAttribute("data-order-id"));
    });

    document.getElementById("orders-filter-form").addEventListener("submit", function (e) {
      e.preventDefault();
      filterOrders();
    });
    document.getElementById("filter-order-id").addEventListener("input", function () {
      filterOrders();
    });

    document.getElementById("orders-table-body").addEventListener("click", function (e) {
      var row = e.target.closest(".order-row");
      if (!row) return;
      selectOrder(row.getAttribute("data-order-id"));
    });

    document.getElementById("shipments-list").addEventListener("click", function (e) {
      var header = e.target.closest(".shipment-header");
      if (!header) return;
      var card = header.closest(".shipment-card");
      var timeline = card.querySelector(".timeline");
      var expanded = !timeline.classList.contains("hidden");
      timeline.classList.toggle("hidden");
      header.setAttribute("aria-expanded", String(!expanded));
      var label = header.querySelector("[data-i18n]");
      if (label) {
        label.textContent = expanded ? t("expand_tracking") + " ▼" : t("collapse_tracking") + " ▲";
      }
    });

    document.getElementById("invoices-table-body").addEventListener("click", function (e) {
      var btn = e.target.closest(".download-summary-btn");
      if (!btn) return;
      showInvoiceSummary(btn.getAttribute("data-invoice-id"));
    });

    document.getElementById("support-next-1").addEventListener("click", function () {
      var cat = document.getElementById("ticket-category").value;
      if (!cat) {
        document.getElementById("ticket-category").focus();
        return;
      }
      state.supportDraft.category = cat;
      setWizardStep(2);
    });

    document.getElementById("support-back-2").addEventListener("click", function () {
      setWizardStep(1);
    });

    document.getElementById("support-next-2").addEventListener("click", function () {
      var subject = document.getElementById("ticket-subject").value.trim();
      var desc = document.getElementById("ticket-description").value.trim();
      if (!subject || !desc) return;
      state.supportDraft.subject = subject;
      state.supportDraft.description = desc;
      document.getElementById("support-review").innerHTML =
        "<p><strong>" +
        t("ticket_category") +
        ":</strong> " +
        document.getElementById("ticket-category").selectedOptions[0].textContent +
        "</p><p><strong>" +
        t("ticket_subject") +
        ":</strong> " +
        subject +
        "</p><p><strong>" +
        t("ticket_description") +
        ":</strong> " +
        desc +
        "</p>";
      setWizardStep(3);
    });

    document.getElementById("support-back-3").addEventListener("click", function () {
      setWizardStep(2);
    });

    document.getElementById("support-submit").addEventListener("click", function () {
      var ticketId = "TKT-" + Date.now().toString(36).toUpperCase();
      var ticketData = {
        ticketId: ticketId,
        category: state.supportDraft.category,
        subject: state.supportDraft.subject,
        description: state.supportDraft.description,
        status: "open",
        createdAt: new Date().toISOString(),
        assignee: "support-team@acme.com",
      };
      document.getElementById("support-step-3").classList.add("hidden");
      document.getElementById("support-success").classList.remove("hidden");
      document.getElementById("ticket-id-display").textContent = ticketId;
      document.getElementById("ticket-json").textContent = JSON.stringify(ticketData, null, 2);
      ["wiz-step-1", "wiz-step-2", "wiz-step-3"].forEach(function (id) {
        document.getElementById(id).classList.add("done");
        document.getElementById(id).classList.remove("active");
      });
    });

    document.querySelectorAll(".lang-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.lang = btn.getAttribute("data-lang");
        document.querySelectorAll(".lang-btn").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        applyI18n();
        renderDashboardOrders();
        if (state.page === "orders") {
          renderOrdersTable();
          if (state.selectedOrderId) {
            var order = ORDERS.find(function (o) {
              return o.id === state.selectedOrderId;
            });
            renderOrderDetail(order);
          }
        }
        if (state.page === "shipments") renderShipments();
        if (state.page === "invoices") renderInvoices();
      });
    });
  }

  function selectOrder(orderId) {
    state.selectedOrderId = orderId;
    document.querySelectorAll(".order-row").forEach(function (row) {
      row.classList.toggle("selected", row.getAttribute("data-order-id") === orderId);
    });
    var order = ORDERS.find(function (o) {
      return o.id === orderId;
    });
    renderOrderDetail(order);
  }

  function init() {
    applyI18n();
    initEvents();
    renderDashboardOrders();
    renderShipments();
    renderInvoices();
    resetSupportWizard();

    if (sessionStorage.getItem("acme_auth") === "1") {
      login();
    } else {
      showView("login");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
