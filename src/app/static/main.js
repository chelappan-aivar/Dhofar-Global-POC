/**
 * main.js
 * Handles data fetching, UI rendering, and navigation interactions.
 * Updated: 2025-12-07 12:02 - Clean Analytics
 */

// --- 1. Core Utilities ----------------------------------------------

// Currency state
let currentCurrency = 'USD';
let currencyRates = {};

// Load currency rates
async function loadCurrencyRates() {
  try {
    const data = await fetchJSON('/api/currencies');
    currencyRates = data.rates || {};
    // Set default currency from localStorage if available
    const savedCurrency = localStorage.getItem('selectedCurrency');
    if (savedCurrency && currencyRates[savedCurrency]) {
      currentCurrency = savedCurrency;
      document.getElementById('currency-selector').value = savedCurrency;
    }
  } catch (e) {
    console.error("Failed to load currency rates:", e);
  }
}

// Convert amount from one currency to another
function convertCurrency(amount, fromCurrency, toCurrency = currentCurrency) {
  if (!amount || !currencyRates[fromCurrency] || !currencyRates[toCurrency]) {
    return amount;
  }
  // Convert to USD first, then to target currency
  const amountInUSD = amount / currencyRates[fromCurrency];
  return amountInUSD * currencyRates[toCurrency];
}

// Change currency and refresh view
window.changeCurrency = async (newCurrency) => {
  currentCurrency = newCurrency;
  localStorage.setItem('selectedCurrency', newCurrency);
  
  // Re-render current view
  const activeNav = document.querySelector('.nav-item.active');
  if (activeNav) {
    const navType = activeNav.id.replace('nav-', '');
    triggerNav(navType);
  }
};

async function fetchJSON(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`API Error: ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error("Fetch failed", url, e);
    return [];
  }
}

async function updateAnalytics() {
  try {
    const [poData, invData, grnData, reconData] = await Promise.all([
      fetchJSON("/api/purchase_orders"),
      fetchJSON("/api/invoices"),
      fetchJSON("/api/goods_receipts"),
      fetchJSON("/api/reconciliation")
    ]);

    // Document counts
    document.getElementById('stat-po').textContent = poData.length;
    document.getElementById('stat-inv').textContent = invData.length;
    document.getElementById('stat-grn').textContent = grnData.length;

    // Reconciliation status counts
    const matched = reconData.filter(r => r.status === 'matched').length;
    const issues = reconData.filter(r => r.status !== 'matched').length;
    
    document.getElementById('stat-matched').textContent = matched;
    document.getElementById('stat-issues').textContent = issues;

    // Decision counts
    const approved = reconData.filter(r => r.decision?.decision === 'approved').length;
    const pending = reconData.filter(r => !r.decision).length;
    
    document.getElementById('stat-approved').textContent = approved;
    document.getElementById('stat-pending').textContent = pending;

    // Show analytics bar
    document.getElementById('analytics-bar').classList.remove('hidden');
  } catch (e) {
    console.error("Failed to update analytics", e);
  }
}

const formatCurrency = (amount, currency = 'USD') => {
  if (amount === null || amount === undefined) return '-';
  try {
    // Convert to selected currency
    const convertedAmount = convertCurrency(amount, currency, currentCurrency);
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currentCurrency }).format(convertedAmount);
  } catch (e) {
    return `${amount} ${currency}`;
  }
};

// --- 2. UI Component Builders ---------------------------------------

function updateHeader(title, count) {
  document.getElementById("page-title").textContent = title;
  document.getElementById("page-count").textContent = `${count} records`;
}

function renderEmptyState(panelId, message) {
  const el = document.getElementById(panelId);
  el.innerHTML = `
    <div class="h-full flex flex-col items-center justify-center text-gray-400 p-6 text-center">
      <span class="text-sm font-medium">${message}</span>
    </div>`;
}

function statusBadge(status) {
  // Normalize status string
  const cleanStatus = (status || "unknown").toLowerCase();
  const label = cleanStatus.replace(/_/g, " ").toUpperCase();
  
  const styles = {
    matched: "bg-green-100 text-green-700 ring-1 ring-green-600/20 shadow-sm",
    missing_invoice: "bg-amber-50 text-amber-700 ring-1 ring-amber-600/20 shadow-sm",
    missing_goods_receipt: "bg-amber-50 text-amber-700 ring-1 ring-amber-600/20 shadow-sm",
    amount_mismatch: "bg-red-50 text-red-700 ring-1 ring-red-600/20 shadow-sm",
    ghost_po: "bg-purple-50 text-purple-700 ring-1 ring-purple-600/20 shadow-sm",
    orphaned_invoice: "bg-orange-50 text-orange-700 ring-1 ring-orange-600/20 shadow-sm",
    orphaned_grn: "bg-orange-50 text-orange-700 ring-1 ring-orange-600/20 shadow-sm",
    default: "bg-gray-100 text-gray-600 ring-1 ring-gray-600/20 shadow-sm"
  };

  const style = styles[cleanStatus] || styles.default;
  return `<span class="inline-flex items-center px-2.5 py-1 rounded-md text-[10px] font-bold tracking-wide ${style}">${label}</span>`;
}

function buildMetaGrid(items) {
  // Creates the top data grid in the Detail Pane
  return `
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
      ${items.map(item => `
        <div class="bg-white p-4 rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-all duration-200 min-w-0">
          <div class="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">${item.label}</div>
          <div class="text-sm font-semibold text-gray-900 overflow-hidden break-words" style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; max-width: 100%; overflow-wrap: break-word; word-wrap: break-word; hyphens: auto;" title="${item.value}">${item.value}</div>
        </div>
      `).join('')}
    </div>
  `;
}

function buildTable(headers, rows) {
  // Creates a clean data table
  return `
    <div class="bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-all duration-200 overflow-hidden mb-6">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gradient-to-r from-gray-50 to-gray-100">
          <tr>
            ${headers.map(h => `
              <th class="px-4 py-3.5 text-left text-[11px] font-bold text-gray-600 uppercase tracking-wider ${h.align === 'right' ? 'text-right' : ''}">
                ${h.label}
              </th>`).join('')}
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100 bg-white">
          ${rows}
        </tbody>
      </table>
    </div>
  `;
}

function buildPDFButton(path) {
  if (!path) {
    return `
      <button disabled class="opacity-50 cursor-not-allowed inline-flex items-center gap-2 px-4 py-2 bg-gray-100 border border-gray-200 rounded-lg text-xs font-semibold text-gray-400">
        No PDF
      </button>`;
  }
  
  return `
    <button onclick="openPdfModal('${encodeURIComponent(path)}')" 
      class="inline-flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-300 hover:bg-gray-50 hover:border-indigo-400 text-gray-700 rounded-lg text-xs font-semibold transition-all duration-200 shadow-sm hover:shadow-md">
      <svg class="w-4 h-4 text-red-500" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd"></path></svg>
      View PDF
    </button>
  `;
}

// PDF Modal Controls
window.openPdfModal = (path) => {
  const modal = document.getElementById('pdf-modal');
  const iframe = document.getElementById('pdf-iframe');
  iframe.src = `/api/pdf?path=${path}`;
  modal.classList.remove('hidden');
};

window.closePdfModal = () => {
  const modal = document.getElementById('pdf-modal');
  const iframe = document.getElementById('pdf-iframe');
  iframe.src = '';
  modal.classList.add('hidden');
};

// --- 3. Page Rendering Logic ----------------------------------------

// A. Reconciliation View (Dashboard)
async function renderRecon(openPoNumber = null) {
  updateHeader("Reconciliation Dashboard", "...");
  
  // Show search bar for reconciliation
  document.getElementById('search-bar').classList.remove('hidden');
  
  renderEmptyState("list-content", "Running 3-way match...");

  const [data, outflowData] = await Promise.all([
    fetchJSON("/api/reconciliation"),
    fetchJSON("/api/outflow_analysis")
  ]);
  
  updateHeader("Reconciliation Dashboard", data.length);
  
  // Store data globally for search and modal access
  window.reconciliationData = data;
  storeReconciliationData(data);
  
  // Update analytics
  updateAnalytics();
  
  if (!data.length) return renderEmptyState("list-content", "No reconciliation tasks found.");

  // Update financial overview in header
  const overall = outflowData.overall || {};
  document.getElementById('finance-po').textContent = formatCurrency(overall.total_po_value);
  document.getElementById('finance-inv').textContent = formatCurrency(overall.total_invoice_value);
  document.getElementById('finance-approved').textContent = formatCurrency(overall.total_approved);
  document.getElementById('finance-pending').textContent = formatCurrency(overall.total_pending);

  // Render List
  renderReconciliationList(data, openPoNumber);
}

function renderReconciliationList(data, openPoNumber = null) {
  const listContent = document.getElementById("list-content");
  listContent.innerHTML = data.map((r, idx) => {
    const po = r.po.purchase_order || {};
    
    // Approval status badge
    const approvalStatus = r.decision 
      ? r.decision.decision 
      : 'pending';
    
    const approvalBadgeStyles = {
      approved: "bg-green-50 text-green-700",
      rejected: "bg-red-50 text-red-700",
      dispute: "bg-orange-50 text-orange-700",
      pending: "bg-gray-50 text-gray-600"
    };
    
    const approvalBadge = `<span class="inline-flex items-center px-2.5 py-1 rounded text-[10px] font-bold tracking-wide uppercase ${approvalBadgeStyles[approvalStatus]}">${approvalStatus}</span>`;
    
    return `
      <div class="list-item group p-5 border-b border-gray-200 hover:bg-gray-50 cursor-pointer transition-all duration-200 border-l-4 border-l-transparent" data-index="${idx}" data-po-number="${po.po_number || ''}">
        <div class="flex justify-between items-start mb-3">
          <h3 class="font-bold text-gray-900 text-base group-hover:text-indigo-600 transition-colors duration-200">${po.po_number || "Unknown PO"}</h3>
          ${approvalBadge}
        </div>
        <div class="text-sm text-gray-600 mb-3 font-medium">${(po.vendor && po.vendor.name) || "Unknown Vendor"}</div>
        <div class="flex gap-2 items-center flex-wrap">
          <span class="inline-flex items-center px-2.5 py-1 rounded-md text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-100">INV: ${r.invoices.length}</span>
          <span class="inline-flex items-center px-2.5 py-1 rounded-md text-[10px] font-semibold bg-teal-50 text-teal-700 border border-teal-100">GRN: ${r.goods_receipts.length}</span>
          ${statusBadge(r.status)}
        </div>
      </div>
    `;
  }).join("");

  // Setup Interaction
  const rows = document.querySelectorAll(".list-item");
  const select = (idx) => {
    rows.forEach(r => r.classList.remove("active"));
    rows[idx].classList.add("active");
    
    const rec = data[idx];
    const po = rec.po.purchase_order || {};
    const detailPanel = document.getElementById("detail-panel");

    // Issues Section with categorization
    const issuesHtml = rec.issues.length 
      ? `<div class="bg-red-50 border border-red-200 rounded-lg p-5 mb-6 shadow-sm">
           <h3 class="text-sm font-bold text-red-800 uppercase tracking-wide mb-3 flex items-center gap-2">
             <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
             Reconciliation Issues (${rec.issues.length})
           </h3>
           <div class="space-y-2">
             ${rec.issues.map((issue, idx) => {
               // Categorize issues by type for better visual distinction
               let iconColor = 'text-red-600';
               let bgColor = 'bg-red-100';
               let icon = '⚠️';
               
               if (issue.includes('Price increased') || issue.includes('Price decreased')) {
                 iconColor = 'text-orange-600';
                 bgColor = 'bg-orange-100';
                 icon = '💰';
               } else if (issue.includes('Quantity mismatch')) {
                 iconColor = 'text-yellow-600';
                 bgColor = 'bg-yellow-100';
                 icon = '📊';
               } else if (issue.includes('Partial delivery') || issue.includes('Over-delivery')) {
                 iconColor = 'text-blue-600';
                 bgColor = 'bg-blue-100';
                 icon = '📦';
               } else if (issue.includes('Missing item') || issue.includes('Unexpected item')) {
                 iconColor = 'text-purple-600';
                 bgColor = 'bg-purple-100';
                 icon = '🔍';
               } else if (issue.includes('Total amount mismatch')) {
                 iconColor = 'text-red-600';
                 bgColor = 'bg-red-100';
                 icon = '💵';
               }
               
               return `
                 <div class="flex items-start gap-3 p-3 ${bgColor} rounded-lg border border-${iconColor.replace('text-', '').replace('-600', '-200')}">
                   <span class="text-lg flex-shrink-0 mt-0.5">${icon}</span>
                   <div class="flex-1">
                     <p class="text-xs font-medium ${iconColor} leading-relaxed">${issue}</p>
                   </div>
                 </div>
               `;
             }).join('')}
           </div>
         </div>` 
      : `<div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-6 flex items-center gap-3 shadow-sm">
           <div class="bg-green-100 p-1.5 rounded-full shadow-sm"><svg class="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg></div>
           <span class="text-xs font-bold text-green-700">Three-way match successful. All items, quantities, and prices validated against Invoice & GRN.</span>
         </div>`;

    // Helper for linked docs
    const renderRelatedDoc = (doc, type) => {
      const isInv = type === 'inv';
      const docData = isInv ? doc.invoice : doc.goods_receipt;
      const id = isInv ? docData.invoice_number : docData.grn_number;
      const refPO = docData.reference_po;
      const docDate = docData.date;
      const vendorName = docData.vendor?.name || 'Unknown';
      const vendorInitial = vendorName.charAt(0).toUpperCase();
      const items = docData.items || [];
      const itemCount = items.length;
      
      const icon = isInv 
        ? '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>'
        : '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"></path>';
      
      // Vendor logo or initial badge
      const vendorBadge = docData.vendor?.logo_url
        ? `<img src="${docData.vendor.logo_url}" alt="${vendorName}" class="w-8 h-8 rounded object-cover border border-gray-200">`
        : `<div class="w-8 h-8 rounded bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center text-white font-bold text-xs">${vendorInitial}</div>`;

      // Build items list
      const itemsHtml = items.slice(0, 3).map(item => `
        <div class="flex justify-between text-[10px] py-1">
          <span class="text-gray-600 truncate flex-1">${item.description}</span>
          <span class="text-gray-900 font-semibold ml-2">×${item.quantity}</span>
        </div>
      `).join('');
      
      const moreItems = itemCount > 3 ? `<div class="text-[9px] text-gray-400 italic">+${itemCount - 3} more items</div>` : '';

      return `
        <div class="p-4 bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md hover:border-indigo-200 transition-all duration-200">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-3">
              ${vendorBadge}
              <div class="bg-indigo-50 text-indigo-600 p-2 rounded-lg shadow-sm">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">${icon}</svg>
              </div>
              <div>
                <div class="text-xs font-bold text-gray-900">${id}</div>
                <div class="text-[10px] text-gray-400 uppercase font-semibold">${isInv ? 'Invoice' : 'Goods Receipt'}</div>
              </div>
            </div>
            <div class="text-right">
               ${isInv ? `<div class="text-xs font-bold text-gray-700">${formatCurrency(docData.grand_total, docData.currency)}</div>` : ''}
               ${docDate ? `<div class="text-[10px] text-gray-400 mt-0.5">${docDate}</div>` : ''}
            </div>
          </div>
          
          <div class="bg-gray-50 rounded-lg p-3 mb-2 border border-gray-100">
            <div class="grid grid-cols-2 gap-2 text-[10px] mb-2">
              <div>
                <span class="text-gray-500">Vendor:</span>
                <div class="font-bold text-gray-900 truncate" title="${vendorName}">${vendorName}</div>
              </div>
              <div>
                <span class="text-gray-500">Ref PO:</span>
                <div class="font-bold text-gray-900">${refPO || '-'}</div>
              </div>
            </div>
            ${isInv ? `
              <div class="grid grid-cols-3 gap-2 text-[10px] pt-2 border-t border-gray-200">
                <div>
                  <span class="text-gray-500">Subtotal:</span>
                  <div class="font-semibold text-gray-900">${formatCurrency(docData.subtotal, docData.currency)}</div>
                </div>
                <div>
                  <span class="text-gray-500">Tax:</span>
                  <div class="font-semibold text-gray-900">${formatCurrency(docData.tax, docData.currency)}</div>
                </div>
                <div>
                  <span class="text-gray-500">Total:</span>
                  <div class="font-bold text-gray-900">${formatCurrency(docData.grand_total, docData.currency)}</div>
                </div>
              </div>
            ` : ''}
          </div>
          
          ${itemCount > 0 ? `
            <div class="bg-gray-50 rounded-lg p-3 mb-2 border border-gray-100">
              <div class="text-[10px] text-gray-400 uppercase font-bold mb-1">Items (${itemCount})</div>
              ${itemsHtml}
              ${moreItems}
            </div>
          ` : ''}
          
          <div class="flex justify-end">
            <button class="text-[10px] text-indigo-600 hover:text-indigo-800 font-bold hover:underline transition-all duration-200" 
              onclick="openPdfModal('${encodeURIComponent(doc.source_pdf_path)}')">View PDF →</button>
          </div>
        </div>
      `;
    };

    // Build PO items table
    const poItemsHtml = (po.items || []).map(it => `
      <tr>
        <td class="px-4 py-3 text-xs font-medium text-gray-900">${it.description}</td>
        <td class="px-4 py-3 text-xs text-right text-gray-600 font-mono">${it.quantity}</td>
        <td class="px-4 py-3 text-xs text-right text-gray-600 font-mono">${formatCurrency(it.unit_price, po.currency)}</td>
        <td class="px-4 py-3 text-xs text-right text-gray-900 font-mono font-bold">${formatCurrency(it.total, po.currency)}</td>
      </tr>
    `).join("");

    // Approval calculation section
    const approvalCalc = rec.approval_calculation || {};
    const hasDeductions = approvalCalc.total_deductions > 0;
    
    const approvalCalculationHtml = approvalCalc.recommended_amount !== undefined ? `
      <div class="bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-200 rounded-lg mb-6 shadow-md overflow-hidden">
        <button onclick="togglePaymentRecommendation(this)" class="w-full p-5 text-left hover:bg-indigo-100 transition-colors duration-200">
          <h3 class="text-sm font-bold text-indigo-900 uppercase tracking-wide flex items-center justify-between gap-2">
            <span class="flex items-center gap-2">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>
              Payment Recommendation
              <span class="text-xs font-normal text-indigo-700 bg-indigo-200 px-2 py-0.5 rounded-full">${formatCurrency(approvalCalc.recommended_amount, po.currency)}</span>
            </span>
            <svg class="w-5 h-5 transform transition-transform duration-200 chevron-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
            </svg>
          </h3>
        </button>
        <div class="payment-calc-content hidden px-5 pb-5">
        
        <div class="grid grid-cols-3 gap-4 mb-4">
          <div class="bg-white rounded-lg p-4 shadow-sm border border-gray-200">
            <div class="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">PO Amount</div>
            <div class="text-lg font-bold text-gray-900">${formatCurrency(approvalCalc.po_amount, po.currency)}</div>
            ${approvalCalc.original_subtotal !== undefined ? `
              <div class="text-[9px] text-gray-500 mt-1">
                Subtotal: ${formatCurrency(approvalCalc.original_subtotal, po.currency)} + Tax: ${formatCurrency(approvalCalc.original_tax, po.currency)}
              </div>
            ` : ''}
          </div>
          <div class="bg-white rounded-lg p-4 shadow-sm border border-gray-200">
            <div class="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Invoice Amount</div>
            <div class="text-lg font-bold text-gray-900">${formatCurrency(approvalCalc.invoice_amount, po.currency)}</div>
            ${approvalCalc.original_subtotal !== undefined ? `
              <div class="text-[9px] text-gray-500 mt-1">
                Subtotal: ${formatCurrency(approvalCalc.original_subtotal, po.currency)} + Tax: ${formatCurrency(approvalCalc.original_tax, po.currency)}
              </div>
            ` : ''}
          </div>
          <div class="bg-gradient-to-br from-green-500 to-emerald-600 rounded-lg p-4 shadow-md">
            <div class="text-[10px] font-bold text-white uppercase tracking-wider mb-1">Recommended</div>
            <div class="text-lg font-bold text-white">${formatCurrency(approvalCalc.recommended_amount, po.currency)}</div>
            ${approvalCalc.adjusted_subtotal !== undefined ? `
              <div class="text-[9px] text-white opacity-90 mt-1">
                Subtotal: ${formatCurrency(approvalCalc.adjusted_subtotal, po.currency)} + Tax: ${formatCurrency(approvalCalc.adjusted_tax, po.currency)}
              </div>
            ` : ''}
          </div>
        </div>
        
        ${hasDeductions ? `
          <div class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-3">
            <div class="flex items-center gap-2 mb-3">
              <svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
              <h4 class="text-sm font-bold text-amber-900">Deductions Required: ${formatCurrency(approvalCalc.total_deductions, po.currency)}</h4>
            </div>
            <div class="space-y-2">
              ${approvalCalc.deduction_details.map(detail => `
                <div class="flex items-start gap-2 text-xs text-amber-800 bg-white rounded p-2 border border-amber-100">
                  <span class="text-amber-600 font-bold">•</span>
                  <span class="flex-1">${detail}</span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
        
        ${approvalCalc.calculation_notes.map(note => `
          <div class="bg-white border border-indigo-200 rounded-lg p-3 text-xs font-medium text-indigo-900">
            💡 ${note}
          </div>
        `).join('')}
        </div>
      </div>
    ` : '';

    // AI Analysis section if exists
    const aiAnalysisHtml = rec.ai_analysis ? `
      <div class="bg-gradient-to-br from-purple-50 to-indigo-50 border border-purple-200 rounded-lg p-5 mb-6">
        <div class="flex items-start gap-3 mb-4">
          <div class="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center flex-shrink-0">
            <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path>
            </svg>
          </div>
          <div class="flex-1">
            <h3 class="text-sm font-bold text-purple-900 mb-1">AI Analysis</h3>
            <div class="flex items-center gap-2 mb-3">
              <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                rec.ai_analysis.risk_level === 'high' ? 'bg-red-100 text-red-700' :
                rec.ai_analysis.risk_level === 'medium' ? 'bg-amber-100 text-amber-700' :
                'bg-green-100 text-green-700'
              }">
                ${rec.ai_analysis.risk_level} Risk
              </span>
              <span class="text-[10px] text-purple-600 font-medium">
                ${rec.ai_analysis.recommendation}
              </span>
            </div>
            <p class="text-sm text-purple-800 mb-3">${rec.ai_analysis.reasoning}</p>
            ${rec.ai_analysis.action_items && rec.ai_analysis.action_items.length > 0 ? `
              <div class="space-y-1.5">
                <div class="text-[10px] font-bold text-purple-700 uppercase tracking-wider">Recommended Actions:</div>
                ${rec.ai_analysis.action_items.map(action => `
                  <div class="flex items-start gap-2 text-xs text-purple-800">
                    <svg class="w-3 h-3 text-purple-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
                    </svg>
                    <span>${action}</span>
                  </div>
                `).join('')}
              </div>
            ` : ''}
            ${rec.ai_analysis.estimated_impact ? `
              <div class="mt-3 pt-3 border-t border-purple-200">
                <div class="text-[10px] font-bold text-purple-700 uppercase tracking-wider mb-1">Estimated Impact:</div>
                <div class="text-xs text-purple-800">${rec.ai_analysis.estimated_impact}</div>
              </div>
            ` : ''}
          </div>
        </div>
        <div class="text-[9px] text-purple-600 flex items-center gap-1">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
          </svg>
          Powered by ${rec.ai_analysis.model || 'OpenAI'}
        </div>
      </div>
    ` : '';

    // Decision badge if exists
    const decisionBadge = rec.decision ? `
      <div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold ${
        rec.decision.decision === 'approved' 
          ? 'bg-green-100 text-green-700 ring-1 ring-green-600/20' 
          : rec.decision.decision === 'dispute'
          ? 'bg-orange-100 text-orange-700 ring-1 ring-orange-600/20'
          : 'bg-red-100 text-red-700 ring-1 ring-red-600/20'
      }">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          ${rec.decision.decision === 'approved' 
            ? '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>'
            : rec.decision.decision === 'dispute'
            ? '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>'
            : '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>'
          }
        </svg>
        ${rec.decision.decision.toUpperCase()}
        <span class="text-[10px] opacity-75">by ${rec.decision.user} at ${new Date(rec.decision.timestamp).toLocaleString()}</span>
      </div>
    ` : '';

    // Vendor logo/initial
    const vendorName = (po.vendor && po.vendor.name) || 'Unknown';
    const vendorInitial = vendorName.charAt(0).toUpperCase();
    const vendorLogo = po.vendor?.logo_url 
      ? `<img src="${po.vendor.logo_url}" alt="${vendorName}" class="w-10 h-10 rounded-lg object-cover border border-gray-200">`
      : `<div class="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-lg">${vendorInitial}</div>`;

    detailPanel.innerHTML = `
      <div class="flex justify-between items-start mb-6">
        <div class="flex gap-4">
          ${vendorLogo}
          <div>
            <div class="flex items-center gap-3 mb-2">
              <h1 class="text-2xl font-bold text-gray-900">${po.po_number || "Unknown PO"}</h1>
              ${statusBadge(rec.status)}
              ${decisionBadge}
            </div>
            <p class="text-sm text-gray-500 font-medium">Vendor: ${vendorName}</p>
            ${rec.decision && rec.decision.comment ? `<p class="text-xs text-gray-500 italic mt-1">Comment: ${rec.decision.comment}</p>` : ''}
          </div>
        </div>
        <div class="flex gap-2 items-center">
          ${rec.decision 
            ? `
              <!-- Already decided - show undo button -->
              <button onclick="handleReconciliationDecision('${po.po_number}', 'undo')" 
                class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-xs font-semibold transition-all duration-200">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"></path></svg>
                Undo
              </button>
            `
            : `
              <!-- Pending - show approve/reject/dispute buttons -->
              <div class="inline-flex rounded-md shadow-sm" role="group">
                <button onclick="handleReconciliationDecision('${po.po_number}', 'approved')" 
                  class="inline-flex items-center gap-1 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-l-md text-xs font-semibold transition-all duration-200 border-r border-green-700">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                  Approve
                </button>
                <button onclick="handleReconciliationDecision('${po.po_number}', 'dispute')" 
                  class="inline-flex items-center gap-1 px-3 py-1.5 bg-orange-600 hover:bg-orange-700 text-white text-xs font-semibold transition-all duration-200 border-r border-orange-700">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                  Dispute
                </button>
                <button onclick="handleReconciliationDecision('${po.po_number}', 'rejected')" 
                  class="inline-flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-r-md text-xs font-semibold transition-all duration-200">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                  Reject
                </button>
              </div>
            `
          }
          ${buildPDFButton(rec.po.source_pdf_path)}
        </div>
      </div>

      ${aiAnalysisHtml}

      ${approvalCalculationHtml}

      ${issuesHtml}

      ${buildMetaGrid([
        { label: "Date", value: po.date || "-" },
        { label: "Buyer", value: (po.buyer && po.buyer.name) || "-" },
        { label: "Ship To", value: (po.buyer && po.buyer.address) || "See PDF" },
        { label: "Total", value: formatCurrency(po.grand_total, po.currency) },
      ])}

      <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Purchase Order Items</h3>
      ${buildTable(
        [ { label: "Description" }, { label: "Qty", align: "right" }, { label: "Unit Price", align: "right" }, { label: "Total", align: "right" } ],
        poItemsHtml
      )}

      <div class="flex justify-end mb-8">
        <div class="w-72 bg-white rounded-lg border border-gray-200 p-6 shadow-md hover:shadow-lg transition-all duration-200 space-y-3">
          <div class="flex justify-between text-xs font-medium text-gray-500"><span>Subtotal</span> <span>${formatCurrency(po.subtotal, po.currency)}</span></div>
          <div class="flex justify-between text-xs font-medium text-gray-500"><span>Tax</span> <span>${formatCurrency(po.tax, po.currency)}</span></div>
          <div class="pt-3 border-t border-gray-100 flex justify-between text-base font-bold text-gray-900"><span>Total</span> <span>${formatCurrency(po.grand_total, po.currency)}</span></div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Linked Invoices</h3>
          <div class="space-y-2">
            ${rec.invoices.length ? rec.invoices.map(d => renderRelatedDoc(d, 'inv')).join('') : '<div class="text-sm text-gray-400 italic bg-white p-4 rounded-lg border border-dashed border-gray-300 shadow-sm">No invoices linked</div>'}
          </div>
        </div>
        <div>
          <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Linked Goods Receipts</h3>
          <div class="space-y-2">
            ${rec.goods_receipts.length ? rec.goods_receipts.map(d => renderRelatedDoc(d, 'grn')).join('') : '<div class="text-sm text-gray-400 italic bg-white p-4 rounded-lg border border-dashed border-gray-300 shadow-sm">No GRNs linked</div>'}
          </div>
        </div>
      </div>
    `;
  };

  rows.forEach((row, idx) => row.addEventListener("click", () => select(idx)));
  
  // Auto-open specific PO if provided
  if (openPoNumber) {
    const targetIndex = data.findIndex(r => {
      const po = r.po.purchase_order || {};
      return po.po_number === openPoNumber;
    });
    if (targetIndex >= 0) {
      select(targetIndex);
      // Scroll to the selected item
      const targetRow = rows[targetIndex];
      if (targetRow) {
        targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    } else if (data.length > 0) {
      select(0);
    }
  } else if (data.length > 0) {
    select(0);
  }
}

// B. Invoices View
async function renderInvoices() {
  updateHeader("Invoices", "...");
  renderEmptyState("list-content", "Loading invoices...");
  
  const data = await fetchJSON("/api/invoices");
  updateHeader("Invoices", data.length);
  
  // Store data globally for search
  window.invoiceData = data;
  
  if (!data.length) return renderEmptyState("list-content", "No invoices found.");

  renderInvoicesList(data);
}

function renderInvoicesList(data) {
  const listContent = document.getElementById("list-content");
  listContent.innerHTML = data.map((d, idx) => {
    const inv = d.invoice || {};
    return `
      <div class="list-item group p-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer border-l-4 border-l-transparent transition-all duration-200" data-index="${idx}">
        <div class="flex justify-between items-start mb-1">
          <span class="font-bold text-gray-900 group-hover:text-indigo-600 transition-colors duration-200 text-sm">${inv.invoice_number || "Draft"}</span>
          <span class="text-xs text-gray-500 font-mono font-semibold">${formatCurrency(inv.grand_total, inv.currency)}</span>
        </div>
        <div class="flex justify-between items-end">
          <div class="text-xs text-gray-500">
            <div class="mb-0.5 truncate w-40 font-medium">${(inv.vendor && inv.vendor.name) || "Unknown"}</div>
            <div class="text-[10px] text-gray-400">PO: ${inv.reference_po || "-"}</div>
          </div>
          <span class="text-[10px] text-gray-400 font-medium">${inv.date || ""}</span>
        </div>
      </div>
    `;
  }).join("");

  const rows = document.querySelectorAll(".list-item");
  const select = (idx) => {
    rows.forEach(r => r.classList.remove("active"));
    rows[idx].classList.add("active");
    
    const d = data[idx];
    const inv = d.invoice || {};
    const detailPanel = document.getElementById("detail-panel");

    const itemsHtml = (inv.items || []).map(it => `
      <tr>
        <td class="px-4 py-3 text-xs font-medium text-gray-900">${it.description}</td>
        <td class="px-4 py-3 text-xs text-right text-gray-600 font-mono">${it.quantity}</td>
        <td class="px-4 py-3 text-xs text-right text-gray-600 font-mono">${formatCurrency(it.unit_price, inv.currency)}</td>
        <td class="px-4 py-3 text-xs text-right text-gray-900 font-mono font-bold">${formatCurrency(it.total, inv.currency)}</td>
      </tr>
    `).join("");

    // Vendor badge
    const vendorName = (inv.vendor && inv.vendor.name) || 'Unknown Vendor';
    const vendorInitial = vendorName.charAt(0).toUpperCase();
    const vendorBadge = `<div class="w-16 h-16 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center text-white font-bold text-2xl shadow-lg">${vendorInitial}</div>`;

    detailPanel.innerHTML = `
      <div class="flex justify-between items-start mb-6">
        <div class="flex items-start gap-4">
          ${vendorBadge}
          <div>
            <h1 class="text-2xl font-bold text-gray-900 mb-1">${inv.invoice_number || "Draft Invoice"}</h1>
            <p class="text-sm text-gray-600 font-medium mb-1">From: ${vendorName}</p>
            ${inv.vendor && inv.vendor.address ? `<p class="text-xs text-gray-500">${inv.vendor.address}</p>` : ''}
          </div>
        </div>
        ${buildPDFButton(d.source_pdf_path)}
      </div>

      ${buildMetaGrid([
        { label: "Invoice Date", value: inv.date || "-" },
        { label: "Reference PO", value: inv.reference_po || "-" },
        { label: "Buyer", value: (inv.buyer && inv.buyer.name) || "-" },
        { label: "Total Amount", value: formatCurrency(inv.grand_total, inv.currency) },
      ])}

      ${inv.buyer && inv.buyer.address ? `
        <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <h3 class="text-xs font-bold text-blue-900 uppercase tracking-wider mb-2">Bill To</h3>
          <p class="text-sm text-blue-800 font-medium">${inv.buyer.name}</p>
          <p class="text-xs text-blue-700 mt-1">${inv.buyer.address}</p>
        </div>
      ` : ''}

      <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Invoice Items</h3>
      ${buildTable(
        [ { label: "Description" }, { label: "Qty", align: "right" }, { label: "Unit Price", align: "right" }, { label: "Total", align: "right" } ],
        itemsHtml
      )}

      <div class="flex justify-end">
        <div class="w-80 bg-gradient-to-br from-gray-50 to-white rounded-lg border border-gray-200 p-6 shadow-md hover:shadow-lg transition-all duration-200 space-y-3">
          <div class="flex justify-between text-sm font-medium text-gray-600">
            <span>Subtotal</span> 
            <span class="font-mono">${formatCurrency(inv.subtotal, inv.currency)}</span>
          </div>
          <div class="flex justify-between text-sm font-medium text-gray-600">
            <span>Tax ${inv.tax_rate ? `(${(inv.tax_rate * 100).toFixed(0)}%)` : ''}</span> 
            <span class="font-mono">${formatCurrency(inv.tax, inv.currency)}</span>
          </div>
          <div class="pt-3 border-t-2 border-gray-300 flex justify-between text-lg font-bold text-gray-900">
            <span>Total Amount</span> 
            <span class="font-mono">${formatCurrency(inv.grand_total, inv.currency)}</span>
          </div>
          ${inv.currency && inv.currency !== 'USD' ? `
            <div class="pt-2 text-xs text-gray-500 text-right">
              Original: ${inv.currency} ${inv.grand_total?.toFixed(2) || '0.00'}
            </div>
          ` : ''}
        </div>
      </div>

      ${inv.notes ? `
        <div class="mt-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <h3 class="text-xs font-bold text-yellow-900 uppercase tracking-wider mb-2">Notes</h3>
          <p class="text-sm text-yellow-800">${inv.notes}</p>
        </div>
      ` : ''}
    `;
  };

  rows.forEach((row, idx) => row.addEventListener("click", () => select(idx)));
  if (data.length > 0) select(0);
}

// C. Purchase Orders View
async function renderPO() {
  updateHeader("Purchase Orders", "...");
  renderEmptyState("list-content", "Loading POs...");

  const data = await fetchJSON("/api/purchase_orders");
  updateHeader("Purchase Orders", data.length);
  
  // Store data globally for search
  window.poData = data;
  
  if (!data.length) return renderEmptyState("list-content", "No POs found.");

  renderPOsList(data);
}

function renderPOsList(data) {
  const listContent = document.getElementById("list-content");
  listContent.innerHTML = data.map((d, idx) => {
    const po = d.purchase_order || {};
    return `
      <div class="list-item group p-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer border-l-4 border-l-transparent transition-all duration-200" data-index="${idx}">
        <div class="flex justify-between items-start mb-1">
          <span class="font-bold text-gray-900 group-hover:text-indigo-600 transition-colors duration-200 text-sm">${po.po_number || "Draft"}</span>
          <span class="text-xs text-gray-500 font-mono font-semibold">${formatCurrency(po.grand_total, po.currency)}</span>
        </div>
        <div class="flex justify-between items-end">
          <div class="text-xs text-gray-500 font-medium truncate w-40">${(po.vendor && po.vendor.name) || "Unknown Vendor"}</div>
          <span class="text-[10px] text-gray-400 font-medium">${po.date || ""}</span>
        </div>
      </div>
    `;
  }).join("");

  const rows = document.querySelectorAll(".list-item");
  const select = (idx) => {
    rows.forEach(r => r.classList.remove("active"));
    rows[idx].classList.add("active");
    
    const d = data[idx];
    const po = d.purchase_order || {};
    const detailPanel = document.getElementById("detail-panel");

    const itemsHtml = (po.items || []).map(it => `
      <tr>
        <td class="px-4 py-3 text-xs font-medium text-gray-900">${it.description}</td>
        <td class="px-4 py-3 text-xs text-right text-gray-600 font-mono">${it.quantity}</td>
        <td class="px-4 py-3 text-xs text-right text-gray-600 font-mono">${formatCurrency(it.unit_price, po.currency)}</td>
        <td class="px-4 py-3 text-xs text-right text-gray-900 font-mono font-bold">${formatCurrency(it.total, po.currency)}</td>
      </tr>
    `).join("");

    detailPanel.innerHTML = `
      <div class="flex justify-between items-start mb-6">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 mb-1">${po.po_number || "Draft PO"}</h1>
          <p class="text-sm text-gray-500 font-medium">Vendor: ${(po.vendor && po.vendor.name)}</p>
        </div>
        ${buildPDFButton(d.source_pdf_path)}
      </div>

      ${buildMetaGrid([
        { label: "Date", value: po.date || "-" },
        { label: "Buyer", value: (po.buyer && po.buyer.name) || "-" },
        { label: "Ship To", value: (po.buyer && po.buyer.address) || "See PDF" },
        { label: "Currency", value: po.currency || "-" },
      ])}

      ${buildTable(
        [ { label: "Description" }, { label: "Qty", align: "right" }, { label: "Unit Price", align: "right" }, { label: "Total", align: "right" } ],
        itemsHtml
      )}

      <div class="flex justify-end">
        <div class="w-72 bg-white rounded-lg border border-gray-200 p-6 shadow-md hover:shadow-lg transition-all duration-200 space-y-3">
          <div class="flex justify-between text-xs font-medium text-gray-500"><span>Subtotal</span> <span>${formatCurrency(po.subtotal, po.currency)}</span></div>
          <div class="flex justify-between text-xs font-medium text-gray-500"><span>Tax</span> <span>${formatCurrency(po.tax, po.currency)}</span></div>
          <div class="pt-3 border-t border-gray-100 flex justify-between text-base font-bold text-gray-900"><span>Total</span> <span>${formatCurrency(po.grand_total, po.currency)}</span></div>
        </div>
      </div>
    `;
  };

  rows.forEach((row, idx) => row.addEventListener("click", () => select(idx)));
  if (data.length > 0) select(0);
}

// D. Goods Receipts View
async function renderGRN() {
  updateHeader("Goods Receipts", "...");
  renderEmptyState("list-content", "Loading GRNs...");

  const data = await fetchJSON("/api/goods_receipts");
  updateHeader("Goods Receipts", data.length);
  
  // Store data globally for search
  window.grnData = data;
  
  if (!data.length) return renderEmptyState("list-content", "No GRNs found.");

  renderGRNsList(data);
}

function renderGRNsList(data) {
  const listContent = document.getElementById("list-content");
  listContent.innerHTML = data.map((d, idx) => {
    const grn = d.goods_receipt || {};
    return `
      <div class="list-item group p-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer border-l-4 border-l-transparent transition-all duration-200" data-index="${idx}">
        <div class="flex justify-between items-start mb-1">
          <span class="font-bold text-gray-900 group-hover:text-indigo-600 transition-colors duration-200 text-sm">${grn.grn_number || "Draft"}</span>
        </div>
        <div class="flex justify-between items-end">
          <div class="text-xs text-gray-500">
            <div class="mb-0.5 font-medium truncate w-40">${(grn.vendor && grn.vendor.name) || "Unknown"}</div>
            <div class="text-[10px] text-gray-400">PO: ${grn.reference_po || "-"}</div>
          </div>
          <span class="text-[10px] text-gray-400 font-medium">${grn.date || ""}</span>
        </div>
      </div>
    `;
  }).join("");

  const rows = document.querySelectorAll(".list-item");
  const select = (idx) => {
    rows.forEach(r => r.classList.remove("active"));
    rows[idx].classList.add("active");
    
    const d = data[idx];
    const grn = d.goods_receipt || {};
    const detailPanel = document.getElementById("detail-panel");

    const itemsHtml = (grn.items || []).map(it => {
      const statusColors = {
        'received': 'bg-green-100 text-green-800',
        'accepted': 'bg-blue-100 text-blue-800',
        'rejected': 'bg-red-100 text-red-800',
        'pending': 'bg-yellow-100 text-yellow-800'
      };
      const status = (it.status || 'received').toLowerCase();
      const statusColor = statusColors[status] || 'bg-gray-100 text-gray-800';
      
      return `
        <tr>
          <td class="px-4 py-3 text-xs font-medium text-gray-900">${it.description}</td>
          <td class="px-4 py-3 text-xs text-right text-gray-600 font-mono font-bold">${it.quantity}</td>
          <td class="px-4 py-3 text-xs text-right">
            <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${statusColor} uppercase tracking-wide">
              ${it.status || "Received"}
            </span>
          </td>
        </tr>
      `;
    }).join("");

    // Vendor badge
    const vendorName = (grn.vendor && grn.vendor.name) || 'Unknown Vendor';
    const vendorInitial = vendorName.charAt(0).toUpperCase();
    const vendorBadge = `<div class="w-16 h-16 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center text-white font-bold text-2xl shadow-lg">${vendorInitial}</div>`;

    // Calculate summary stats
    const totalItems = grn.items?.length || 0;
    const totalQuantity = (grn.items || []).reduce((sum, item) => sum + (item.quantity || 0), 0);
    const receivedItems = (grn.items || []).filter(item => (item.status || 'received').toLowerCase() === 'received').length;
    const acceptedItems = (grn.items || []).filter(item => (item.status || '').toLowerCase() === 'accepted').length;
    const rejectedItems = (grn.items || []).filter(item => (item.status || '').toLowerCase() === 'rejected').length;

    detailPanel.innerHTML = `
      <div class="flex justify-between items-start mb-6">
        <div class="flex items-start gap-4">
          ${vendorBadge}
          <div>
            <h1 class="text-2xl font-bold text-gray-900 mb-1">${grn.grn_number || "Draft GRN"}</h1>
            <p class="text-sm text-gray-600 font-medium mb-1">From: ${vendorName}</p>
            <p class="text-xs text-gray-500">Reference PO: ${grn.reference_po || "N/A"}</p>
          </div>
        </div>
        ${buildPDFButton(d.source_pdf_path)}
      </div>

      ${buildMetaGrid([
        { label: "Receipt Date", value: grn.date || "-" },
        { label: "Vendor", value: vendorName },
        { label: "Received By", value: (grn.buyer && grn.buyer.name) || "-" },
        { label: "Total Items", value: totalItems },
      ])}

      ${grn.buyer && grn.buyer.address ? `
        <div class="bg-teal-50 border border-teal-200 rounded-lg p-4 mb-6">
          <h3 class="text-xs font-bold text-teal-900 uppercase tracking-wider mb-2">Delivery Location</h3>
          <p class="text-sm text-teal-800 font-medium">${grn.buyer.name}</p>
          <p class="text-xs text-teal-700 mt-1">${grn.buyer.address}</p>
        </div>
      ` : ''}

      ${rejectedItems > 0 ? `
        <!-- Inspection Summary -->
        <div class="mb-6">
          <div class="bg-red-50 rounded-lg p-4 border border-red-200 shadow-sm inline-block">
            <div class="text-xs font-bold text-red-700 uppercase tracking-wider mb-1">Rejected Items</div>
            <div class="text-2xl font-bold text-red-900">${rejectedItems}</div>
          </div>
        </div>
      ` : ''}

      <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Received Items</h3>
      ${buildTable(
        [ { label: "Description" }, { label: "Qty Received", align: "right" }, { label: "Inspection Status", align: "right" } ],
        itemsHtml
      )}

      ${grn.notes ? `
        <div class="mt-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <h3 class="text-xs font-bold text-yellow-900 uppercase tracking-wider mb-2">Delivery Notes</h3>
          <p class="text-sm text-yellow-800">${grn.notes}</p>
        </div>
      ` : ''}

      ${grn.receiver_signature ? `
        <div class="mt-6 bg-gray-50 border border-gray-200 rounded-lg p-4">
          <h3 class="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">Received & Inspected By</h3>
          <p class="text-sm text-gray-800 font-medium">${grn.receiver_signature}</p>
          <p class="text-xs text-gray-500 mt-1">${grn.date || ''}</p>
        </div>
      ` : ''}
    `;
  };

  rows.forEach((row, idx) => row.addEventListener("click", () => select(idx)));
  if (data.length > 0) select(0);
}

// E. Vendors View (merged with scores)
async function renderVendors() {
  console.log("renderVendors called");
  updateHeader("Vendors", "...");
  renderEmptyState("list-content", "Loading vendors...");

  // Fetch both vendors data and scores
  const [vendorsData, scoresData] = await Promise.all([
    fetchJSON("/api/vendors"),
    fetchJSON("/api/vendor_scores")
  ]);
  
  console.log("Vendors data:", vendorsData);
  updateHeader("Vendors", vendorsData.length);
  if (!vendorsData.length) return renderEmptyState("list-content", "No vendors found.");

  // Create a map of scores by vendor name
  const scoresMap = {};
  scoresData.forEach(score => {
    scoresMap[score.vendor_name] = score;
  });

  const listContent = document.getElementById("list-content");
  listContent.innerHTML = vendorsData.map((vendor, idx) => {
    const vendorInitial = vendor.name.charAt(0).toUpperCase();
    const vendorBadge = vendor.logo_url
      ? `<img src="${vendor.logo_url}" alt="${vendor.name}" class="w-10 h-10 rounded-lg object-cover border border-gray-200">`
      : `<div class="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center text-white font-bold text-base">${vendorInitial}</div>`;

    // Get score data if available
    const scoreData = scoresMap[vendor.name];
    const score = scoreData ? scoreData.score : null;
    const rating = scoreData ? scoreData.rating : null;
    
    const scoreColor = score >= 90 ? 'text-green-700' : score >= 75 ? 'text-blue-700' : score >= 60 ? 'text-yellow-700' : 'text-red-700';
    const scoreBg = score >= 90 ? 'bg-green-50' : score >= 75 ? 'bg-blue-50' : score >= 60 ? 'bg-yellow-50' : 'bg-red-50';
    const scoreRing = score >= 90 ? 'ring-green-600/20' : score >= 75 ? 'ring-blue-600/20' : score >= 60 ? 'ring-yellow-600/20' : 'ring-red-600/20';

    return `
      <div class="list-item group p-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer border-l-4 border-l-transparent transition-all duration-200" data-index="${idx}">
        <div class="flex items-center gap-3 mb-3">
          ${vendorBadge}
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <h3 class="font-bold text-gray-900 group-hover:text-indigo-600 transition-colors duration-200 text-sm">${vendor.name}</h3>
              ${score !== null ? `
                <span class="text-xs font-bold ${scoreColor} ${scoreBg} px-2 py-0.5 rounded-full ring-1 ${scoreRing}">${score}</span>
              ` : ''}
            </div>
            <div class="text-[10px] text-gray-500 font-medium">${vendor.invoice_count} invoice${vendor.invoice_count !== 1 ? 's' : ''}${rating ? ` • ${rating}` : ''}</div>
          </div>
        </div>
        <div class="flex justify-between items-center">
          <span class="text-xs text-gray-500 font-medium">Total Amount</span>
          <span class="text-sm font-bold text-gray-900">${formatCurrency(vendor.total_amount)}</span>
        </div>
      </div>
    `;
  }).join("");

  const rows = document.querySelectorAll(".list-item");
  const select = (idx) => {
    rows.forEach(r => r.classList.remove("active"));
    rows[idx].classList.add("active");
    
    const vendor = vendorsData[idx];
    const scoreData = scoresMap[vendor.name];
    const detailPanel = document.getElementById("detail-panel");

    // Vendor header
    const vendorInitial = vendor.name.charAt(0).toUpperCase();
    const vendorLogo = vendor.logo_url 
      ? `<img src="${vendor.logo_url}" alt="${vendor.name}" class="w-16 h-16 rounded-xl object-cover border-2 border-gray-200 shadow-md">`
      : `<div class="w-16 h-16 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center text-white font-bold text-2xl shadow-md">${vendorInitial}</div>`;

    // Build invoice cards
    const invoiceCards = vendor.invoices.map(invDoc => {
      const inv = invDoc.invoice || {};
      return `
        <div class="bg-white border border-gray-200 rounded-lg p-4 shadow-sm hover:shadow-md transition-all duration-200">
          <div class="flex justify-between items-start mb-3">
            <div>
              <h4 class="font-bold text-gray-900 text-sm mb-1">${inv.invoice_number || "Draft"}</h4>
              <div class="text-[10px] text-gray-500 font-medium">PO: ${inv.reference_po || "-"}</div>
            </div>
            <div class="text-right">
              <div class="text-sm font-bold text-gray-900">${formatCurrency(inv.grand_total, inv.currency)}</div>
              <div class="text-[10px] text-gray-400 mt-0.5">${inv.date || ""}</div>
            </div>
          </div>
          
          <div class="bg-gray-50 rounded-lg p-3 mb-3 border border-gray-100">
            <div class="grid grid-cols-3 gap-2 text-[10px]">
              <div>
                <span class="text-gray-500">Subtotal:</span>
                <div class="font-semibold text-gray-900">${formatCurrency(inv.subtotal, inv.currency)}</div>
              </div>
              <div>
                <span class="text-gray-500">Tax:</span>
                <div class="font-semibold text-gray-900">${formatCurrency(inv.tax, inv.currency)}</div>
              </div>
              <div>
                <span class="text-gray-500">Total:</span>
                <div class="font-bold text-gray-900">${formatCurrency(inv.grand_total, inv.currency)}</div>
              </div>
            </div>
          </div>

          ${inv.items && inv.items.length > 0 ? `
            <div class="bg-gray-50 rounded-lg p-3 mb-3 border border-gray-100">
              <div class="text-[10px] text-gray-400 uppercase font-bold mb-2">Items (${inv.items.length})</div>
              ${inv.items.slice(0, 3).map(item => `
                <div class="flex justify-between text-[10px] py-1">
                  <span class="text-gray-600 truncate flex-1">${item.description}</span>
                  <span class="text-gray-900 font-semibold ml-2">×${item.quantity}</span>
                </div>
              `).join('')}
              ${inv.items.length > 3 ? `<div class="text-[9px] text-gray-400 italic mt-1">+${inv.items.length - 3} more items</div>` : ''}
            </div>
          ` : ''}

          <div class="flex justify-end">
            <button class="text-[10px] text-indigo-600 hover:text-indigo-800 font-bold hover:underline transition-all duration-200" 
              onclick="openPdfModal('${encodeURIComponent(invDoc.source_pdf_path)}')">View PDF →</button>
          </div>
        </div>
      `;
    }).join('');

    detailPanel.innerHTML = `
      <div class="flex items-start gap-6 mb-6">
        ${vendorLogo}
        <div class="flex-1">
          <h1 class="text-3xl font-bold text-gray-900 mb-2">${vendor.name}</h1>
          <div class="flex gap-3 items-center flex-wrap">
            <span class="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-100">
              ${vendor.invoice_count} Invoice${vendor.invoice_count !== 1 ? 's' : ''}
            </span>
            <span class="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-green-50 text-green-700 border border-green-100">
              Total: ${formatCurrency(vendor.total_amount)}
            </span>
            ${scoreData ? `
              <span class="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold ${
                scoreData.score >= 90 ? 'bg-green-50 text-green-700 border border-green-100' :
                scoreData.score >= 75 ? 'bg-blue-50 text-blue-700 border border-blue-100' :
                scoreData.score >= 60 ? 'bg-yellow-50 text-yellow-700 border border-yellow-100' :
                'bg-red-50 text-red-700 border border-red-100'
              }">
                Score: ${scoreData.score} (${scoreData.rating})
              </span>
            ` : ''}
          </div>
        </div>
      </div>

      ${scoreData ? `
        <div class="bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-200 rounded-lg p-5 mb-6">
          <h3 class="text-sm font-bold text-indigo-900 mb-4 flex items-center gap-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
            Performance Metrics
          </h3>
          <div class="grid grid-cols-4 gap-3">
            <div class="bg-white rounded-lg p-3 border border-gray-200">
              <div class="text-[10px] text-gray-500 uppercase font-bold mb-1">On-Time Rate</div>
              <div class="text-lg font-bold ${scoreData.on_time_deliveries > scoreData.late_deliveries ? 'text-green-600' : 'text-red-600'}">
                ${((scoreData.on_time_deliveries / (scoreData.on_time_deliveries + scoreData.late_deliveries || 1)) * 100).toFixed(0)}%
              </div>
              <div class="text-[9px] text-gray-500">${scoreData.on_time_deliveries}/${scoreData.on_time_deliveries + scoreData.late_deliveries}</div>
            </div>
            <div class="bg-white rounded-lg p-3 border border-gray-200">
              <div class="text-[10px] text-gray-500 uppercase font-bold mb-1">Avg Delivery</div>
              <div class="text-lg font-bold text-gray-900">${Math.round(scoreData.avg_delivery_days)}d</div>
              <div class="text-[9px] text-gray-500">${scoreData.delivery_count} deliveries</div>
            </div>
            <div class="bg-white rounded-lg p-3 border border-gray-200">
              <div class="text-[10px] text-gray-500 uppercase font-bold mb-1">Price Accuracy</div>
              <div class="text-lg font-bold ${scoreData.price_matches > scoreData.price_mismatches ? 'text-green-600' : 'text-red-600'}">
                ${((scoreData.price_matches / (scoreData.price_matches + scoreData.price_mismatches || 1)) * 100).toFixed(0)}%
              </div>
              <div class="text-[9px] text-gray-500">${scoreData.price_matches}/${scoreData.price_matches + scoreData.price_mismatches}</div>
            </div>
            <div class="bg-white rounded-lg p-3 border border-gray-200">
              <div class="text-[10px] text-gray-500 uppercase font-bold mb-1">Clean Invoices</div>
              <div class="text-lg font-bold ${scoreData.clean_invoices > scoreData.issues_found ? 'text-green-600' : 'text-red-600'}">
                ${((scoreData.clean_invoices / (scoreData.clean_invoices + scoreData.issues_found || 1)) * 100).toFixed(0)}%
              </div>
              <div class="text-[9px] text-gray-500">${scoreData.clean_invoices}/${scoreData.clean_invoices + scoreData.issues_found}</div>
            </div>
          </div>
        </div>
      ` : ''}

      <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4">Invoices from ${vendor.name}</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        ${invoiceCards}
      </div>
    `;
  };

  rows.forEach((row, idx) => row.addEventListener("click", () => select(idx)));
  if (vendorsData.length > 0) select(0);
}

// F. Buyers View (merged with outflow analysis)
async function renderBuyers() {
  console.log("renderBuyers called");
  updateHeader("Buyers & Outflow", "...");
  renderEmptyState("list-content", "Loading buyers...");

  const [buyersData, outflowData] = await Promise.all([
    fetchJSON("/api/buyers"),
    fetchJSON("/api/outflow_analysis")
  ]);
  
  console.log("Buyers data:", buyersData);
  updateHeader("Buyers & Outflow", buyersData.length);
  if (!buyersData.length) return renderEmptyState("list-content", "No buyers found.");

  // Create a map of outflow data by buyer name
  const outflowMap = {};
  (outflowData.by_buyer || []).forEach(buyer => {
    outflowMap[buyer.buyer_name] = buyer;
  });

  const listContent = document.getElementById("list-content");
  listContent.innerHTML = buyersData.map((buyer, idx) => {
    const buyerInitial = buyer.name.charAt(0).toUpperCase();
    const buyerBadge = `<div class="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center text-white font-bold text-base">${buyerInitial}</div>`;

    // Get outflow data for this buyer
    const outflow = outflowMap[buyer.name] || {};
    const approved = outflow.total_approved || 0;
    const pending = outflow.total_pending || 0;

    return `
      <div class="list-item group p-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer border-l-4 border-l-transparent transition-all duration-200" data-index="${idx}">
        <div class="flex items-center gap-3 mb-3">
          ${buyerBadge}
          <div class="flex-1">
            <h3 class="font-bold text-gray-900 group-hover:text-indigo-600 transition-colors duration-200 text-sm">${buyer.name}</h3>
            <div class="text-[10px] text-gray-500 font-medium">${buyer.po_count} PO${buyer.po_count !== 1 ? 's' : ''} • ${buyer.grn_count} GRN${buyer.grn_count !== 1 ? 's' : ''}</div>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-2 text-xs">
          <div class="text-center p-2 bg-blue-50 rounded">
            <div class="font-bold text-blue-700">${formatCurrency(buyer.total_po_value)}</div>
            <div class="text-gray-500 text-[9px]">PO Value</div>
          </div>
          <div class="text-center p-2 bg-green-50 rounded">
            <div class="font-bold text-green-700">${formatCurrency(approved)}</div>
            <div class="text-gray-500 text-[9px]">Approved</div>
          </div>
          <div class="text-center p-2 bg-yellow-50 rounded">
            <div class="font-bold text-yellow-700">${formatCurrency(pending)}</div>
            <div class="text-gray-500 text-[9px]">Pending</div>
          </div>
        </div>
      </div>
    `;
  }).join("");

  const rows = document.querySelectorAll(".list-item");
  const select = (idx) => {
    rows.forEach(r => r.classList.remove("active"));
    rows[idx].classList.add("active");
    
    const buyer = buyersData[idx];
    const outflow = outflowMap[buyer.name] || {};
    const detailPanel = document.getElementById("detail-panel");

    // Buyer header
    const buyerInitial = buyer.name.charAt(0).toUpperCase();
    const buyerLogo = `<div class="w-16 h-16 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center text-white font-bold text-2xl shadow-md">${buyerInitial}</div>`;

    // Build PO cards
    const poCards = buyer.purchase_orders.map(poDoc => {
      const po = poDoc.purchase_order || {};
      return `
        <div class="bg-white border border-gray-200 rounded-lg p-4 shadow-sm hover:shadow-md transition-all duration-200">
          <div class="flex justify-between items-start mb-3">
            <div>
              <h4 class="font-bold text-gray-900 text-sm mb-1">${po.po_number || "Draft"}</h4>
              <div class="text-[10px] text-gray-500 font-medium">Vendor: ${(po.vendor && po.vendor.name) || "-"}</div>
            </div>
            <div class="text-right">
              <div class="text-sm font-bold text-gray-900">${formatCurrency(po.grand_total, po.currency)}</div>
              <div class="text-[10px] text-gray-400 mt-0.5">${po.date || ""}</div>
            </div>
          </div>
          
          <div class="bg-gray-50 rounded-lg p-3 mb-3 border border-gray-100">
            <div class="grid grid-cols-3 gap-2 text-[10px]">
              <div>
                <span class="text-gray-500">Subtotal:</span>
                <div class="font-semibold text-gray-900">${formatCurrency(po.subtotal, po.currency)}</div>
              </div>
              <div>
                <span class="text-gray-500">Tax:</span>
                <div class="font-semibold text-gray-900">${formatCurrency(po.tax, po.currency)}</div>
              </div>
              <div>
                <span class="text-gray-500">Total:</span>
                <div class="font-bold text-gray-900">${formatCurrency(po.grand_total, po.currency)}</div>
              </div>
            </div>
          </div>

          ${po.items && po.items.length > 0 ? `
            <div class="bg-gray-50 rounded-lg p-3 mb-3 border border-gray-100">
              <div class="text-[10px] text-gray-400 uppercase font-bold mb-2">Items (${po.items.length})</div>
              ${po.items.slice(0, 3).map(item => `
                <div class="flex justify-between text-[10px] py-1">
                  <span class="text-gray-600 truncate flex-1">${item.description}</span>
                  <span class="text-gray-900 font-semibold ml-2">×${item.quantity}</span>
                </div>
              `).join('')}
              ${po.items.length > 3 ? `<div class="text-[9px] text-gray-400 italic mt-1">+${po.items.length - 3} more items</div>` : ''}
            </div>
          ` : ''}

          <div class="flex justify-end">
            <button class="text-[10px] text-indigo-600 hover:text-indigo-800 font-bold hover:underline transition-all duration-200" 
              onclick="openPdfModal('${encodeURIComponent(poDoc.source_pdf_path)}')">View PDF →</button>
          </div>
        </div>
      `;
    }).join('');

    // Build GRN cards
    const grnCards = buyer.goods_receipts.map(grnDoc => {
      const grn = grnDoc.goods_receipt || {};
      return `
        <div class="bg-white border border-gray-200 rounded-lg p-4 shadow-sm hover:shadow-md transition-all duration-200">
          <div class="flex justify-between items-start mb-3">
            <div>
              <h4 class="font-bold text-gray-900 text-sm mb-1">${grn.grn_number || "Draft"}</h4>
              <div class="text-[10px] text-gray-500 font-medium">PO: ${grn.reference_po || "-"}</div>
            </div>
            <div class="text-right">
              <div class="text-[10px] text-gray-400 mt-0.5">${grn.date || ""}</div>
            </div>
          </div>

          ${grn.items && grn.items.length > 0 ? `
            <div class="bg-gray-50 rounded-lg p-3 mb-3 border border-gray-100">
              <div class="text-[10px] text-gray-400 uppercase font-bold mb-2">Items Received (${grn.items.length})</div>
              ${grn.items.slice(0, 3).map(item => `
                <div class="flex justify-between text-[10px] py-1">
                  <span class="text-gray-600 truncate flex-1">${item.description}</span>
                  <span class="text-gray-900 font-semibold ml-2">×${item.quantity}</span>
                </div>
              `).join('')}
              ${grn.items.length > 3 ? `<div class="text-[9px] text-gray-400 italic mt-1">+${grn.items.length - 3} more items</div>` : ''}
            </div>
          ` : ''}

          <div class="flex justify-end">
            <button class="text-[10px] text-indigo-600 hover:text-indigo-800 font-bold hover:underline transition-all duration-200" 
              onclick="openPdfModal('${encodeURIComponent(grnDoc.source_pdf_path)}')">View PDF →</button>
          </div>
        </div>
      `;
    }).join('');

    detailPanel.innerHTML = `
      <div class="flex items-start gap-6 mb-6">
        ${buyerLogo}
        <div class="flex-1">
          <h1 class="text-3xl font-bold text-gray-900 mb-2">${buyer.name}</h1>
          ${buyer.country ? `<p class="text-sm text-gray-500 mb-2">${buyer.country}</p>` : ''}
          ${buyer.address ? `<p class="text-xs text-gray-500 mb-3">${buyer.address}</p>` : ''}
          <div class="flex gap-3 items-center flex-wrap">
            <span class="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-100">
              ${buyer.po_count} Purchase Order${buyer.po_count !== 1 ? 's' : ''}
            </span>
            <span class="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-teal-50 text-teal-700 border border-teal-100">
              ${buyer.grn_count} Goods Receipt${buyer.grn_count !== 1 ? 's' : ''}
            </span>
            <span class="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-green-50 text-green-700 border border-green-100">
              Total: ${formatCurrency(buyer.total_amount)}
            </span>
          </div>
        </div>
      </div>

      ${outflow.total_po_value ? `
        <div class="bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-200 rounded-lg p-5 mb-6">
          <h3 class="text-sm font-bold text-indigo-900 mb-4 flex items-center gap-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"></path></svg>
            Cash Outflow Analysis
          </h3>
          <div class="grid grid-cols-4 gap-3 mb-4">
            <div class="bg-white rounded-lg p-3 border border-gray-200">
              <div class="text-[10px] text-gray-500 uppercase font-bold mb-1">PO Value</div>
              <div class="text-lg font-bold text-blue-600">${formatCurrency(outflow.total_po_value)}</div>
            </div>
            <div class="bg-white rounded-lg p-3 border border-gray-200">
              <div class="text-[10px] text-gray-500 uppercase font-bold mb-1">Invoice Value</div>
              <div class="text-lg font-bold text-purple-600">${formatCurrency(outflow.total_invoice_value || 0)}</div>
            </div>
            <div class="bg-white rounded-lg p-3 border border-gray-200">
              <div class="text-[10px] text-gray-500 uppercase font-bold mb-1">Approved</div>
              <div class="text-lg font-bold text-green-600">${formatCurrency(outflow.total_approved)}</div>
            </div>
            <div class="bg-white rounded-lg p-3 border border-gray-200">
              <div class="text-[10px] text-gray-500 uppercase font-bold mb-1">Pending</div>
              <div class="text-lg font-bold text-yellow-600">${formatCurrency(outflow.total_pending)}</div>
            </div>
          </div>
          ${outflow.by_vendor && Object.keys(outflow.by_vendor).length > 0 ? `
            <div class="bg-white rounded-lg p-3 border border-gray-200">
              <div class="text-[10px] text-gray-500 uppercase font-bold mb-2">Top Vendors by Spend</div>
              <div class="space-y-1">
                ${Object.entries(outflow.by_vendor).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([vendor, amount]) => `
                  <div class="flex justify-between text-xs">
                    <span class="text-gray-700">${vendor}</span>
                    <span class="font-bold text-gray-900">${formatCurrency(amount)}</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}
        </div>
      ` : ''}

      ${buyer.purchase_orders.length > 0 ? `
        <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4">Purchase Orders</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          ${poCards}
        </div>
      ` : ''}

      ${buyer.goods_receipts.length > 0 ? `
        <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4">Goods Receipts</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          ${grnCards}
        </div>
      ` : ''}
    `;
  };

  rows.forEach((row, idx) => row.addEventListener("click", () => select(idx)));
  if (buyersData.length > 0) select(0);
}

// Toggle Payment Recommendation section
window.togglePaymentRecommendation = (button) => {
  const content = button.nextElementSibling;
  const chevron = button.querySelector('.chevron-icon');
  
  if (content.classList.contains('hidden')) {
    content.classList.remove('hidden');
    chevron.style.transform = 'rotate(180deg)';
  } else {
    content.classList.add('hidden');
    chevron.style.transform = 'rotate(0deg)';
  }
};

// G. Vendor Scores View
async function renderVendorScores() {
  updateHeader("Vendor Performance Scores", "...");
  document.getElementById("list-panel").innerHTML = '<div class="p-8 text-center text-gray-500">Loading vendor scores...</div>';
  document.getElementById("detail-panel").innerHTML = '';

  const data = await fetchJSON("/api/vendor_scores");
  updateHeader("Vendor Performance Scores", data.length);
  
  if (!data.length) {
    document.getElementById("list-panel").innerHTML = '<div class="p-8 text-center text-gray-500">No vendor data available.</div>';
    return;
  }

  const listPanel = document.getElementById("list-panel");
  listPanel.innerHTML = `
    <div class="p-6">
      <h3 class="text-lg font-bold text-gray-900 mb-4">Vendor Rankings</h3>
      <div class="space-y-3">
        ${data.map((vendor, idx) => {
          const scoreColor = vendor.score >= 90 ? 'green' : vendor.score >= 75 ? 'blue' : vendor.score >= 60 ? 'yellow' : 'red';
          const bgColor = vendor.score >= 90 ? 'bg-green-50' : vendor.score >= 75 ? 'bg-blue-50' : vendor.score >= 60 ? 'bg-yellow-50' : 'bg-red-50';
          const textColor = vendor.score >= 90 ? 'text-green-700' : vendor.score >= 75 ? 'text-blue-700' : vendor.score >= 60 ? 'text-yellow-700' : 'text-red-700';
          const ringColor = vendor.score >= 90 ? 'ring-green-600/20' : vendor.score >= 75 ? 'ring-blue-600/20' : vendor.score >= 60 ? 'ring-yellow-600/20' : 'ring-red-600/20';
          
          return `
            <div class="vendor-score-item p-4 bg-white border border-gray-200 rounded-lg hover:shadow-md transition-all duration-200 cursor-pointer" data-index="${idx}">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-3">
                  <div class="text-2xl font-bold text-gray-400">#${idx + 1}</div>
                  <div>
                    <h4 class="font-bold text-gray-900">${vendor.vendor_name}</h4>
                    <div class="text-xs text-gray-500">${vendor.total_pos} POs • ${formatCurrency(vendor.total_value)}</div>
                  </div>
                </div>
                <div class="text-right">
                  <div class="text-3xl font-bold ${textColor}">${vendor.score}</div>
                  <div class="text-xs font-semibold ${textColor} ${bgColor} px-2 py-0.5 rounded-full ring-1 ${ringColor}">${vendor.rating}</div>
                </div>
              </div>
              <div class="grid grid-cols-4 gap-2 mt-3 text-xs">
                <div class="text-center p-2 bg-gray-50 rounded">
                  <div class="font-bold text-gray-900">${vendor.on_time_deliveries}/${vendor.on_time_deliveries + vendor.late_deliveries}</div>
                  <div class="text-gray-500">On-Time</div>
                </div>
                <div class="text-center p-2 bg-gray-50 rounded">
                  <div class="font-bold text-gray-900">${Math.round(vendor.avg_delivery_days)}d</div>
                  <div class="text-gray-500">Avg Delivery</div>
                </div>
                <div class="text-center p-2 bg-gray-50 rounded">
                  <div class="font-bold text-gray-900">${vendor.price_matches}/${vendor.price_matches + vendor.price_mismatches}</div>
                  <div class="text-gray-500">Price Match</div>
                </div>
                <div class="text-center p-2 bg-gray-50 rounded">
                  <div class="font-bold text-gray-900">${vendor.clean_invoices}/${vendor.clean_invoices + vendor.issues_found}</div>
                  <div class="text-gray-500">Clean Inv</div>
                </div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;

  const detailPanel = document.getElementById("detail-panel");
  detailPanel.innerHTML = `
    <div class="p-8">
      <h3 class="text-2xl font-bold text-gray-900 mb-6">Vendor Scoring Methodology</h3>
      
      <div class="space-y-4 mb-8">
        <div class="bg-gradient-to-r from-blue-50 to-indigo-50 border border-indigo-200 rounded-lg p-4">
          <h4 class="font-bold text-indigo-900 mb-2">📊 Score Breakdown (Total: 100 points)</h4>
          <div class="space-y-2 text-sm">
            <div class="flex justify-between">
              <span class="text-gray-700">• Delivery Performance (On-time rate)</span>
              <span class="font-bold text-indigo-900">40 points</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-700">• Price Accuracy (Matches PO pricing)</span>
              <span class="font-bold text-indigo-900">30 points</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-700">• Quantity Accuracy (Matches PO quantities)</span>
              <span class="font-bold text-indigo-900">20 points</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-700">• Invoice Cleanliness (No reconciliation issues)</span>
              <span class="font-bold text-indigo-900">10 points</span>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-3">
          <div class="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-green-700">90-100</div>
            <div class="text-xs font-semibold text-green-600">Excellent</div>
          </div>
          <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-blue-700">75-89</div>
            <div class="text-xs font-semibold text-blue-600">Good</div>
          </div>
          <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-yellow-700">60-74</div>
            <div class="text-xs font-semibold text-yellow-600">Fair</div>
          </div>
          <div class="bg-red-50 border border-red-200 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-red-700">0-59</div>
            <div class="text-xs font-semibold text-red-600">Poor</div>
          </div>
        </div>
      </div>

      <div class="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h4 class="font-bold text-gray-900 mb-2">📝 Notes</h4>
        <ul class="text-sm text-gray-700 space-y-1">
          <li>• Scores are calculated based on historical reconciliation data</li>
          <li>• On-time delivery is defined as ≤30 days from PO date</li>
          <li>• Price and quantity matches must be exact (within $0.01)</li>
          <li>• Higher scores indicate more reliable vendors</li>
        </ul>
      </div>
    </div>
  `;

  // Add click handlers
  document.querySelectorAll('.vendor-score-item').forEach((item, idx) => {
    item.addEventListener('click', () => {
      const vendor = data[idx];
      detailPanel.innerHTML = `
        <div class="p-8">
          <div class="flex items-start justify-between mb-6">
            <div>
              <h2 class="text-3xl font-bold text-gray-900 mb-2">${vendor.vendor_name}</h2>
              <div class="text-sm text-gray-500">${vendor.total_pos} Purchase Orders • ${formatCurrency(vendor.total_value)} Total Value</div>
            </div>
            <div class="text-right">
              <div class="text-5xl font-bold ${vendor.score >= 90 ? 'text-green-600' : vendor.score >= 75 ? 'text-blue-600' : vendor.score >= 60 ? 'text-yellow-600' : 'text-red-600'}">${vendor.score}</div>
              <div class="text-sm font-bold ${vendor.score >= 90 ? 'text-green-600' : vendor.score >= 75 ? 'text-blue-600' : vendor.score >= 60 ? 'text-yellow-600' : 'text-red-600'}">${vendor.rating}</div>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="bg-white border border-gray-200 rounded-lg p-4">
              <h4 class="text-xs font-bold text-gray-500 uppercase mb-3">Delivery Performance</h4>
              <div class="space-y-2">
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">On-Time Deliveries:</span>
                  <span class="font-bold text-green-600">${vendor.on_time_deliveries}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Late Deliveries:</span>
                  <span class="font-bold text-red-600">${vendor.late_deliveries}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Average Delivery Time:</span>
                  <span class="font-bold text-gray-900">${Math.round(vendor.avg_delivery_days)} days</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">On-Time Rate:</span>
                  <span class="font-bold text-gray-900">${((vendor.on_time_deliveries / (vendor.on_time_deliveries + vendor.late_deliveries || 1)) * 100).toFixed(1)}%</span>
                </div>
              </div>
            </div>

            <div class="bg-white border border-gray-200 rounded-lg p-4">
              <h4 class="text-xs font-bold text-gray-500 uppercase mb-3">Invoice Accuracy</h4>
              <div class="space-y-2">
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Price Matches:</span>
                  <span class="font-bold text-green-600">${vendor.price_matches}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Price Mismatches:</span>
                  <span class="font-bold text-red-600">${vendor.price_mismatches}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Quantity Matches:</span>
                  <span class="font-bold text-green-600">${vendor.quantity_matches}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Quantity Mismatches:</span>
                  <span class="font-bold text-red-600">${vendor.quantity_mismatches}</span>
                </div>
              </div>
            </div>

            <div class="bg-white border border-gray-200 rounded-lg p-4">
              <h4 class="text-xs font-bold text-gray-500 uppercase mb-3">Overall Quality</h4>
              <div class="space-y-2">
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Clean Invoices:</span>
                  <span class="font-bold text-green-600">${vendor.clean_invoices}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Issues Found:</span>
                  <span class="font-bold text-red-600">${vendor.issues_found}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Clean Rate:</span>
                  <span class="font-bold text-gray-900">${((vendor.clean_invoices / (vendor.clean_invoices + vendor.issues_found || 1)) * 100).toFixed(1)}%</span>
                </div>
              </div>
            </div>

            <div class="bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-200 rounded-lg p-4">
              <h4 class="text-xs font-bold text-indigo-900 uppercase mb-3">Recommendation</h4>
              <div class="text-sm text-indigo-800">
                ${vendor.score >= 90 ? '✅ Highly recommended vendor with excellent performance across all metrics.' : 
                  vendor.score >= 75 ? '👍 Reliable vendor with good overall performance.' :
                  vendor.score >= 60 ? '⚠️ Acceptable vendor but monitor for improvements.' :
                  '❌ Consider reviewing relationship or implementing improvement plans.'}
              </div>
            </div>
          </div>
        </div>
      `;
    });
  });
}

// H. Outflow Analysis View
async function renderOutflowAnalysis() {
  updateHeader("Cash Outflow Analysis", "...");
  document.getElementById("list-panel").innerHTML = '<div class="p-8 text-center text-gray-500">Loading outflow data...</div>';
  document.getElementById("detail-panel").innerHTML = '';

  const data = await fetchJSON("/api/outflow_analysis");
  updateHeader("Cash Outflow Analysis", "Overall + Buyers");
  
  const overall = data.overall || {};
  const buyers = data.by_buyer || [];

  // Render overall summary in list panel
  const listPanel = document.getElementById("list-panel");
  listPanel.innerHTML = `
    <div class="p-6">
      <h3 class="text-lg font-bold text-gray-900 mb-4">Overall Outflow Summary</h3>
      <div class="grid grid-cols-2 gap-4 mb-6">
        <div class="bg-gradient-to-br from-blue-50 to-indigo-50 border border-indigo-200 rounded-lg p-4">
          <div class="text-xs font-bold text-indigo-600 uppercase mb-1">Total PO Value</div>
          <div class="text-2xl font-bold text-indigo-900">${formatCurrency(overall.total_po_value)}</div>
        </div>
        <div class="bg-gradient-to-br from-purple-50 to-pink-50 border border-purple-200 rounded-lg p-4">
          <div class="text-xs font-bold text-purple-600 uppercase mb-1">Total Invoice Value</div>
          <div class="text-2xl font-bold text-purple-900">${formatCurrency(overall.total_invoice_value)}</div>
        </div>
        <div class="bg-gradient-to-br from-green-50 to-emerald-50 border border-green-200 rounded-lg p-4">
          <div class="text-xs font-bold text-green-600 uppercase mb-1">Approved</div>
          <div class="text-2xl font-bold text-green-900">${formatCurrency(overall.total_approved)}</div>
        </div>
        <div class="bg-gradient-to-br from-yellow-50 to-amber-50 border border-yellow-200 rounded-lg p-4">
          <div class="text-xs font-bold text-yellow-600 uppercase mb-1">Pending</div>
          <div class="text-2xl font-bold text-yellow-900">${formatCurrency(overall.total_pending)}</div>
        </div>
      </div>

      <h3 class="text-lg font-bold text-gray-900 mb-4 mt-6">By Buyer</h3>
      <div class="space-y-3">
        ${buyers.map((buyer, idx) => `
          <div class="buyer-outflow-item p-4 bg-white border border-gray-200 rounded-lg hover:shadow-md transition-all duration-200 cursor-pointer" data-index="${idx}">
            <div class="flex justify-between items-start mb-2">
              <div>
                <h4 class="font-bold text-gray-900">${buyer.buyer_name}</h4>
                <div class="text-xs text-gray-500">${buyer.po_count} Purchase Orders</div>
              </div>
              <div class="text-right">
                <div class="text-lg font-bold text-gray-900">${formatCurrency(buyer.total_po_value)}</div>
              </div>
            </div>
            <div class="grid grid-cols-3 gap-2 mt-2 text-xs">
              <div class="text-center p-2 bg-green-50 rounded">
                <div class="font-bold text-green-700">${formatCurrency(buyer.total_approved)}</div>
                <div class="text-gray-500">Approved</div>
              </div>
              <div class="text-center p-2 bg-yellow-50 rounded">
                <div class="font-bold text-yellow-700">${formatCurrency(buyer.total_pending)}</div>
                <div class="text-gray-500">Pending</div>
              </div>
              <div class="text-center p-2 bg-red-50 rounded">
                <div class="font-bold text-red-700">${formatCurrency(buyer.total_rejected)}</div>
                <div class="text-gray-500">Rejected</div>
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;

  // Render detailed breakdown in detail panel
  const detailPanel = document.getElementById("detail-panel");
  detailPanel.innerHTML = `
    <div class="p-8">
      <h3 class="text-2xl font-bold text-gray-900 mb-6">Outflow Breakdown</h3>
      
      <div class="mb-6">
        <h4 class="text-sm font-bold text-gray-700 uppercase mb-3">By Currency</h4>
        <div class="grid grid-cols-3 gap-3">
          ${Object.entries(overall.by_currency || {}).map(([currency, amount]) => `
            <div class="bg-white border border-gray-200 rounded-lg p-3">
              <div class="text-xs text-gray-500">${currency}</div>
              <div class="text-lg font-bold text-gray-900">${formatCurrency(amount, currency)}</div>
            </div>
          `).join('')}
        </div>
      </div>

      <div class="mb-6">
        <h4 class="text-sm font-bold text-gray-700 uppercase mb-3">Top Vendors by Spend</h4>
        <div class="space-y-2">
          ${Object.entries(overall.by_vendor || {})
            .sort((a, b) => b[1] - a[1])
            .slice(0, 10)
            .map(([vendor, amount]) => `
              <div class="flex justify-between items-center p-3 bg-white border border-gray-200 rounded-lg">
                <span class="text-sm font-medium text-gray-700">${vendor}</span>
                <span class="text-sm font-bold text-gray-900">${formatCurrency(amount)}</span>
              </div>
            `).join('')}
        </div>
      </div>
    </div>
  `;

  // Add click handlers for buyer details
  document.querySelectorAll('.buyer-outflow-item').forEach((item, idx) => {
    item.addEventListener('click', () => {
      const buyer = buyers[idx];
      detailPanel.innerHTML = `
        <div class="p-8">
          <h2 class="text-3xl font-bold text-gray-900 mb-6">${buyer.buyer_name}</h2>
          
          <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="bg-white border border-gray-200 rounded-lg p-4">
              <h4 class="text-xs font-bold text-gray-500 uppercase mb-3">Payment Status</h4>
              <div class="space-y-2">
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Total PO Value:</span>
                  <span class="font-bold text-gray-900">${formatCurrency(buyer.total_po_value)}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Approved:</span>
                  <span class="font-bold text-green-600">${formatCurrency(buyer.total_approved)}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Pending:</span>
                  <span class="font-bold text-yellow-600">${formatCurrency(buyer.total_pending)}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-600">Rejected:</span>
                  <span class="font-bold text-red-600">${formatCurrency(buyer.total_rejected)}</span>
                </div>
              </div>
            </div>

            <div class="bg-white border border-gray-200 rounded-lg p-4">
              <h4 class="text-xs font-bold text-gray-500 uppercase mb-3">By Currency</h4>
              <div class="space-y-2">
                ${Object.entries(buyer.by_currency || {}).map(([currency, amount]) => `
                  <div class="flex justify-between text-sm">
                    <span class="text-gray-600">${currency}:</span>
                    <span class="font-bold text-gray-900">${formatCurrency(amount, currency)}</span>
                  </div>
                `).join('')}
              </div>
            </div>
          </div>

          <div>
            <h4 class="text-sm font-bold text-gray-700 uppercase mb-3">Spend by Vendor</h4>
            <div class="space-y-2">
              ${Object.entries(buyer.by_vendor || {})
                .sort((a, b) => b[1] - a[1])
                .map(([vendor, amount]) => `
                  <div class="flex justify-between items-center p-3 bg-white border border-gray-200 rounded-lg">
                    <span class="text-sm font-medium text-gray-700">${vendor}</span>
                    <span class="text-sm font-bold text-gray-900">${formatCurrency(amount)}</span>
                  </div>
                `).join('')}
            </div>
          </div>
        </div>
      `;
    });
  });
}

// --- 4. Reconciliation Decision Handler ----------------------------

let pendingDecision = null;
let currentReconciliationData = null;

// Store reconciliation data when rendering
function storeReconciliationData(data) {
  currentReconciliationData = data;
}

window.handleReconciliationDecision = (poNumber, decision) => {
  // Handle undo action — remove row from reconciliation_decisions in MongoDB
  if (decision === 'undo') {
    if (confirm(`Are you sure you want to undo the decision for ${poNumber}?`)) {
      void (async () => {
        try {
          const response = await fetch(
            `/api/reconciliation/decision/${encodeURIComponent(poNumber)}`,
            { method: 'DELETE' }
          );
          if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${response.status}`);
          }
          showToast(`Decision cleared for ${poNumber}`, 'success');
          await renderRecon();
        } catch (error) {
          console.error('Error clearing decision:', error);
          showToast(`Failed to clear decision: ${error.message}`, 'error');
        }
      })();
    }
    return;
  }
  
  // Find the reconciliation record for this PO
  const rec = currentReconciliationData?.find(r => {
    const po = r.po?.purchase_order || {};
    return po.po_number === poNumber;
  });
  
  // Store decision details
  pendingDecision = { poNumber, decision, reconciliation: rec };
  
  // Update modal title and button
  const modal = document.getElementById('comment-modal');
  const modalTitle = document.getElementById('modal-title');
  const submitBtn = document.getElementById('modal-submit-btn');
  const commentInput = document.getElementById('comment-input');
  const modalCalculation = document.getElementById('modal-calculation');
  
  const decisionLabels = {
    approved: 'Approve',
    rejected: 'Reject',
    dispute: 'Dispute'
  };
  const buttonLabels = {
    approved: 'Approve Payment',
    rejected: 'Reject Payment',
    dispute: 'Mark as Disputed'
  };
  const buttonColors = {
    approved: 'bg-green-600 hover:bg-green-700',
    rejected: 'bg-red-600 hover:bg-red-700',
    dispute: 'bg-orange-600 hover:bg-orange-700'
  };
  
  modalTitle.textContent = `${decisionLabels[decision] || decision} ${poNumber}`;
  submitBtn.textContent = buttonLabels[decision] || 'Submit';
  submitBtn.className = `flex-1 px-4 py-2.5 rounded-lg font-medium text-sm text-white transition-all duration-200 shadow-md hover:shadow-lg ${buttonColors[decision] || 'bg-gray-600 hover:bg-gray-700'}`;
  
  // Build calculation display
  if (rec && rec.approval_calculation) {
    const calc = rec.approval_calculation;
    const po = rec.po?.purchase_order || {};
    const currency = po.currency || 'USD';
    const hasDeductions = calc.total_deductions > 0;
    
    modalCalculation.innerHTML = `
      <div class="bg-gradient-to-br from-blue-50 to-indigo-50 border border-indigo-200 rounded-lg p-4 mb-4">
        <h4 class="text-sm font-bold text-indigo-900 mb-3 flex items-center gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>
          Payment Calculation
        </h4>
        
        <div class="space-y-2 mb-3">
          <div class="bg-white rounded border border-gray-200 p-2">
            <div class="flex justify-between items-center mb-1">
              <span class="text-xs font-medium text-gray-600">Purchase Order Amount:</span>
              <span class="text-sm font-bold text-gray-900">${formatCurrency(calc.po_amount, currency)}</span>
            </div>
            ${calc.original_subtotal !== undefined ? `
              <div class="text-[10px] text-gray-500 pl-2">
                (Subtotal: ${formatCurrency(calc.original_subtotal, currency)} + Tax: ${formatCurrency(calc.original_tax, currency)} @ ${(calc.tax_rate * 100).toFixed(1)}%)
              </div>
            ` : ''}
          </div>
          <div class="bg-white rounded border border-gray-200 p-2">
            <div class="flex justify-between items-center mb-1">
              <span class="text-xs font-medium text-gray-600">Invoice Amount:</span>
              <span class="text-sm font-bold text-gray-900">${formatCurrency(calc.invoice_amount, currency)}</span>
            </div>
            ${calc.original_subtotal !== undefined ? `
              <div class="text-[10px] text-gray-500 pl-2">
                (Subtotal: ${formatCurrency(calc.original_subtotal, currency)} + Tax: ${formatCurrency(calc.original_tax, currency)})
              </div>
            ` : ''}
          </div>
          ${hasDeductions ? `
            <div class="flex justify-between items-center p-2 bg-amber-50 rounded border border-amber-300">
              <span class="text-xs font-medium text-amber-800">Subtotal Deductions:</span>
              <span class="text-sm font-bold text-amber-900">- ${formatCurrency(calc.total_deductions, currency)}</span>
            </div>
            ${calc.tax_adjustment > 0.01 ? `
              <div class="flex justify-between items-center p-2 bg-amber-50 rounded border border-amber-300">
                <span class="text-xs font-medium text-amber-800">Tax Adjustment:</span>
                <span class="text-sm font-bold text-amber-900">- ${formatCurrency(calc.tax_adjustment, currency)}</span>
              </div>
            ` : ''}
          ` : ''}
          <div class="bg-gradient-to-r from-green-500 to-emerald-600 rounded shadow-md p-3">
            <div class="flex justify-between items-center mb-1">
              <span class="text-xs font-bold text-white uppercase tracking-wide">Recommended Amount:</span>
              <span class="text-lg font-bold text-white">${formatCurrency(calc.recommended_amount, currency)}</span>
            </div>
            ${calc.adjusted_subtotal !== undefined ? `
              <div class="text-[10px] text-white opacity-90 pl-2">
                (Subtotal: ${formatCurrency(calc.adjusted_subtotal, currency)} + Tax: ${formatCurrency(calc.adjusted_tax, currency)} @ ${(calc.tax_rate * 100).toFixed(1)}%)
              </div>
            ` : ''}
          </div>
        </div>
        
        ${hasDeductions ? `
          <div class="bg-white border border-amber-200 rounded-lg p-3 mb-2">
            <div class="text-xs font-bold text-amber-900 mb-2 flex items-center gap-1">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
              Deduction Breakdown:
            </div>
            <div class="space-y-1.5">
              ${calc.deduction_details.map(detail => `
                <div class="text-xs text-amber-800 bg-amber-50 rounded p-2 border border-amber-100">
                  • ${detail}
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
        
        <div class="bg-indigo-100 border border-indigo-300 rounded-lg p-3 text-xs font-medium text-indigo-900">
          💡 ${calc.calculation_notes[0] || 'Review the calculation above before proceeding.'}
        </div>
      </div>
    `;
  } else {
    modalCalculation.innerHTML = '';
  }
  
  // Clear previous comment and show modal
  commentInput.value = '';
  modal.classList.remove('hidden');
};

window.closeCommentModal = () => {
  document.getElementById('comment-modal').classList.add('hidden');
  pendingDecision = null;
};

window.submitDecision = async () => {
  if (!pendingDecision) return;
  
  const comment = document.getElementById('comment-input').value.trim();
  const { poNumber, decision } = pendingDecision;
  
  // Close modal
  closeCommentModal();
  
  try {
    const response = await fetch('/api/reconciliation/decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        po_number: poNumber,
        decision: decision,
        comment: comment || ''
      })
    });
    
    if (!response.ok) {
      throw new Error(`Failed to save decision: ${response.status}`);
    }
    
    const result = await response.json();
    
    // Show success toast
    showToast(`✓ Reconciliation ${decision} for ${poNumber}`, 'success');
    
    // Refresh the reconciliation view and analytics
    renderRecon();
    
  } catch (error) {
    console.error('Error saving decision:', error);
    showToast(`Failed to save decision: ${error.message}`, 'error');
  }
};

// Toast notification helper
function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `fixed top-4 right-4 px-6 py-3.5 rounded-lg shadow-xl text-white font-medium text-sm z-50 transform transition-all duration-300 border ${
    type === 'success' ? 'bg-green-600 border-green-700' : 'bg-red-600 border-red-700'
  }`;
  toast.textContent = message;
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-10px)';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// --- 5. Sidebar Toggle ---------------------------------------------

window.toggleSidebar = () => {
  const sidebar = document.getElementById('sidebar');
  const sidebarHeader = document.getElementById('sidebar-header');
  const sidebarTitle = document.getElementById('sidebar-title');
  const sidebarIcon = document.getElementById('sidebar-icon');
  const navTexts = document.querySelectorAll('.nav-text');
  const navLabels = document.querySelectorAll('.nav-label');
  const sectionHeaders = document.querySelectorAll('.nav-section-header');
  
  const isCollapsed = sidebar.classList.contains('w-24');
  
  if (isCollapsed) {
    // Expand
    sidebar.classList.remove('w-24');
    sidebar.classList.add('w-64');
    sidebarHeader.classList.remove('px-2');
    sidebarHeader.classList.add('px-6');
    sidebarTitle.classList.remove('hidden');
    navTexts.forEach(el => el.classList.remove('hidden'));
    navLabels.forEach(el => el.classList.remove('hidden'));
    sectionHeaders.forEach(el => el.classList.remove('hidden'));
    sidebarIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7m8 14l-7-7 7-7"></path>';
  } else {
    // Collapse
    sidebar.classList.remove('w-64');
    sidebar.classList.add('w-24');
    sidebarHeader.classList.remove('px-6');
    sidebarHeader.classList.add('px-2');
    sidebarTitle.classList.add('hidden');
    navTexts.forEach(el => el.classList.add('hidden'));
    navLabels.forEach(el => el.classList.add('hidden'));
    sectionHeaders.forEach(el => el.classList.add('hidden'));
    sidebarIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7M5 5l7 7-7 7"></path>';
  }
};

// --- 6. Navigation & Initialization ---------------------------------

// Global search state
let currentView = null;

// Generic search handler
window.handleSearch = (searchTerm) => {
  const term = searchTerm.toLowerCase().trim();
  const clearBtn = document.getElementById('clear-search-btn');
  
  // Show/hide clear button
  if (term) {
    clearBtn.classList.remove('hidden');
  } else {
    clearBtn.classList.add('hidden');
  }
  
  // Route to appropriate filter function based on current view
  switch(currentView) {
    case 'customer_cards':
      filterCustomerCards(term);
      break;
    case 'eft_payments':
      filterEFTPayments(term);
      break;
    case 'dhofar_recon':
      filterDhofarRecon(term);
      break;
  }
};

// Filter reconciliation
function filterReconciliation(term) {
  if (!window.reconciliationData) return;
  
  const filteredData = term 
    ? window.reconciliationData.filter(r => {
        const po = r.po.purchase_order || {};
        const poNumber = (po.po_number || '').toLowerCase();
        const vendorName = ((po.vendor && po.vendor.name) || '').toLowerCase();
        return poNumber.includes(term) || vendorName.includes(term);
      })
    : window.reconciliationData;
  
  renderReconciliationList(filteredData);
}

// Filter invoices
function filterInvoices(term) {
  if (!window.invoiceData) return;
  
  const filteredData = term 
    ? window.invoiceData.filter(d => {
        const inv = d.invoice || {};
        const invNumber = (inv.invoice_number || '').toLowerCase();
        const vendorName = ((inv.vendor && inv.vendor.name) || '').toLowerCase();
        const refPO = (inv.reference_po || '').toLowerCase();
        return invNumber.includes(term) || vendorName.includes(term) || refPO.includes(term);
      })
    : window.invoiceData;
  
  renderInvoicesList(filteredData);
}

// Filter POs
function filterPOs(term) {
  if (!window.poData) return;
  
  const filteredData = term 
    ? window.poData.filter(d => {
        const po = d.purchase_order || {};
        const poNumber = (po.po_number || '').toLowerCase();
        const vendorName = ((po.vendor && po.vendor.name) || '').toLowerCase();
        const buyerName = ((po.buyer && po.buyer.name) || '').toLowerCase();
        return poNumber.includes(term) || vendorName.includes(term) || buyerName.includes(term);
      })
    : window.poData;
  
  renderPOsList(filteredData);
}

// Filter GRNs
function filterGRNs(term) {
  if (!window.grnData) return;
  
  const filteredData = term 
    ? window.grnData.filter(d => {
        const grn = d.goods_receipt || {};
        const grnNumber = (grn.grn_number || '').toLowerCase();
        const vendorName = ((grn.vendor && grn.vendor.name) || '').toLowerCase();
        const refPO = (grn.reference_po || '').toLowerCase();
        return grnNumber.includes(term) || vendorName.includes(term) || refPO.includes(term);
      })
    : window.grnData;
  
  renderGRNsList(filteredData);
}

window.clearSearch = () => {
  document.getElementById('search-input').value = '';
  document.getElementById('clear-search-btn').classList.add('hidden');
  handleSearch('');
};

window.triggerNav = (type) => {
  console.log("triggerNav called with type:", type);
  // Update UI Sidebar
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active', 'border-indigo-500', 'bg-gray-800', 'text-white'));
  const btn = document.getElementById(`nav-${type}`);
  if(btn) btn.classList.add('active');
  
  // Set current view for search
  currentView = type;
  
  // Show/hide search bar based on view type
  const searchableViews = ['customer_cards', 'eft_payments', 'dhofar_recon'];
  const searchBar = document.getElementById('search-bar');
  const searchInput = document.getElementById('search-input');
  
  if (searchableViews.includes(type)) {
    searchBar.classList.remove('hidden');
    const placeholders = {
      'customer_cards': 'Search by customer name or ID...',
      'eft_payments': 'Search by reference or date...',
      'dhofar_recon': 'Search by remitter or customer name...',
    };
    searchInput.placeholder = placeholders[type] || 'Search...';
  } else {
    searchBar.classList.add('hidden');
  }
  
  // Clear search when switching views
  searchInput.value = '';
  document.getElementById('clear-search-btn').classList.add('hidden');

  // Route
  if (type === 'customer_cards') renderCustomerCards();
  if (type === 'eft_payments') renderEFTPayments();
  if (type === 'dhofar_recon') renderDhofarReconciliation();
};

// Initialize app
window.addEventListener("DOMContentLoaded", async () => {
  triggerNav('dhofar_recon'); // Default View
  setupDropZone(); // Setup drag and drop
});

// --- Upload Modal Handlers ---

let selectedFiles = [];
let uploadContext = null; // 'customer_card' | 'eft' | null (auto-detect)

window.openUploadModal = (context) => {
  uploadContext = context || null;
  const modal = document.getElementById('upload-modal');
  modal.classList.remove('hidden');
  resetUploadModal();

  // Update modal hint based on context
  const hint = document.getElementById('upload-hint');
  if (hint) {
    if (context === 'customer_card') {
      hint.textContent = 'Upload a Customer Card PDF. It will be processed as a customer account statement.';
      document.getElementById('file-input').accept = '.pdf';
    } else if (context === 'eft') {
      hint.textContent = 'Upload an EFT Excel file (.xlsx). Payment rows will be extracted automatically.';
      document.getElementById('file-input').accept = '.xlsx,.xls';
    } else {
      hint.textContent = 'Upload a PDF (Invoice, PO, GRN, Customer Card) or Excel (EFT). The system auto-classifies.';
      document.getElementById('file-input').accept = '.pdf,.xlsx,.xls';
    }
  }
};

window.closeUploadModal = () => {
  const modal = document.getElementById('upload-modal');
  modal.classList.add('hidden');
  resetUploadModal();
};

function resetUploadModal() {
  selectedFiles = [];
  document.getElementById('file-input').value = '';
  document.getElementById('selected-files').classList.add('hidden');
  document.getElementById('upload-progress').classList.add('hidden');
  document.getElementById('upload-result').classList.add('hidden');
  document.getElementById('upload-btn').disabled = true;
  document.getElementById('drop-zone').classList.remove('hidden');
}

window.handleFileSelect = (event) => {
  const files = Array.from(event.target.files);
  if (files.length > 0) {
    displaySelectedFiles(files);
  }
};

function displaySelectedFiles(files) {
  // Validate all files
  const validFiles = [];
  const errors = [];
  
  files.forEach(file => {
    const isPdf = file.name.toLowerCase().endsWith('.pdf');
    const isExcel = file.name.toLowerCase().endsWith('.xlsx') || file.name.toLowerCase().endsWith('.xls');
    if (!isPdf && !isExcel) {
      errors.push(`${file.name}: Not a PDF or Excel file`);
    } else if (file.size > 10 * 1024 * 1024) {
      errors.push(`${file.name}: File size exceeds 10MB`);
    } else {
      validFiles.push(file);
    }
  });
  
  if (errors.length > 0) {
    alert('Some files were skipped:\n' + errors.join('\n'));
  }
  
  if (validFiles.length === 0) {
    return;
  }
  
  selectedFiles = validFiles;
  
  // Display files list
  const filesList = document.getElementById('files-list');
  filesList.innerHTML = validFiles.map((file, index) => `
    <div class="flex items-center justify-between p-3 bg-white border border-indigo-200 rounded-lg">
      <div class="flex items-center gap-3 flex-1 min-w-0">
        <svg class="w-6 h-6 text-red-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd"></path>
        </svg>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-semibold text-gray-900 truncate" title="${file.name}">${file.name}</p>
          <p class="text-xs text-gray-500">${formatFileSize(file.size)}</p>
        </div>
      </div>
      <button onclick="removeFile(${index})" class="text-gray-400 hover:text-red-600 flex-shrink-0 ml-2">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
        </svg>
      </button>
    </div>
  `).join('');
  
  document.getElementById('file-count').textContent = validFiles.length;
  document.getElementById('selected-files').classList.remove('hidden');
  document.getElementById('upload-btn').disabled = false;
  document.getElementById('drop-zone').classList.add('hidden');
}

window.removeFile = (index) => {
  selectedFiles.splice(index, 1);
  if (selectedFiles.length === 0) {
    clearFileSelection();
  } else {
    displaySelectedFiles(selectedFiles);
  }
};

window.clearFileSelection = () => {
  selectedFiles = [];
  document.getElementById('file-input').value = '';
  document.getElementById('selected-files').classList.add('hidden');
  document.getElementById('upload-btn').disabled = true;
  document.getElementById('drop-zone').classList.remove('hidden');
};

function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

window.uploadFile = async () => {
  if (selectedFiles.length === 0) {
    alert('Please select at least one file');
    return;
  }
  
  // Show progress
  document.getElementById('upload-progress').classList.remove('hidden');
  document.getElementById('upload-btn').disabled = true;
  document.getElementById('upload-result').classList.add('hidden');
  
  const totalFiles = selectedFiles.length;
  let completedFiles = 0;
  const results = [];
  
  // Update progress text
  const updateProgress = () => {
    const percentage = Math.round((completedFiles / totalFiles) * 100);
    document.getElementById('progress-bar').style.width = percentage + '%';
    document.getElementById('progress-text').textContent = `${completedFiles} / ${totalFiles}`;
  };
  
  updateProgress();
  
  // Process files sequentially to avoid overwhelming the API
  for (let i = 0; i < selectedFiles.length; i++) {
    const file = selectedFiles[i];
    const fileId = `file-${i}`;
    
    // Add file to progress details
    const progressDetails = document.getElementById('progress-details');
    const fileProgressDiv = document.createElement('div');
    fileProgressDiv.id = fileId;
    fileProgressDiv.className = 'p-3 bg-gray-50 border border-gray-200 rounded-lg';
    fileProgressDiv.innerHTML = `
      <div class="flex items-center gap-2">
        <div class="animate-spin rounded-full h-4 w-4 border-2 border-indigo-600 border-t-transparent"></div>
        <span class="text-xs font-medium text-gray-700 flex-1 truncate">${file.name}</span>
        <span class="text-xs text-gray-500">Processing...</span>
      </div>
    `;
    progressDetails.appendChild(fileProgressDiv);
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      // Route to correct endpoint based on context or file type
      const isExcel = file.name.toLowerCase().endsWith('.xlsx') || file.name.toLowerCase().endsWith('.xls');
      let endpoint;
      if (uploadContext === 'customer_card' || uploadContext === 'eft') {
        endpoint = '/api/upload_dhofar';
      } else if (isExcel) {
        endpoint = '/api/upload_dhofar';
      } else {
        endpoint = '/api/upload';
      }
      
      const response = await fetch(endpoint, {
        method: 'POST',
        body: formData
      });
      
      const result = await response.json();
      
      if (response.ok && result.success) {
        // Success
        fileProgressDiv.className = 'p-3 bg-green-50 border border-green-200 rounded-lg';
        fileProgressDiv.innerHTML = `
          <div class="flex items-center gap-2">
            <svg class="w-4 h-4 text-green-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
            </svg>
            <span class="text-xs font-medium text-gray-900 flex-1 truncate" title="${file.name}">${file.name}</span>
            <span class="text-xs text-green-700 font-semibold">${result.document_type.replace(/_/g, ' ')}</span>
          </div>
        `;
        results.push({ success: true, file: file.name, result });
      } else {
        // Error
        const errorMsg = result.detail || result.message || 'Upload failed';
        fileProgressDiv.className = 'p-3 bg-red-50 border border-red-200 rounded-lg';
        fileProgressDiv.innerHTML = `
          <div class="flex items-center gap-2">
            <svg class="w-4 h-4 text-red-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
            <span class="text-xs font-medium text-gray-900 flex-1 truncate" title="${file.name}">${file.name}</span>
            <span class="text-xs text-red-700">Failed</span>
          </div>
          <p class="text-xs text-red-600 mt-1 ml-6">${errorMsg}</p>
        `;
        results.push({ success: false, file: file.name, error: errorMsg });
      }
      
    } catch (error) {
      console.error('Upload error:', error);
      fileProgressDiv.className = 'p-3 bg-red-50 border border-red-200 rounded-lg';
      fileProgressDiv.innerHTML = `
        <div class="flex items-center gap-2">
          <svg class="w-4 h-4 text-red-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
          <span class="text-xs font-medium text-gray-900 flex-1 truncate" title="${file.name}">${file.name}</span>
          <span class="text-xs text-red-700">Error</span>
        </div>
        <p class="text-xs text-red-600 mt-1 ml-6">${error.message}</p>
      `;
      results.push({ success: false, file: file.name, error: error.message });
    }
    
    completedFiles++;
    updateProgress();
  }
  
  // Show summary
  const successCount = results.filter(r => r.success).length;
  const failCount = results.filter(r => !r.success).length;
  
  document.getElementById('upload-result').innerHTML = `
    <div class="p-4 ${successCount === totalFiles ? 'bg-green-50 border-green-200' : 'bg-blue-50 border-blue-200'} border rounded-lg">
      <div class="flex items-start gap-3">
        <svg class="w-6 h-6 ${successCount === totalFiles ? 'text-green-600' : 'text-blue-600'} flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>
        <div class="flex-1">
          <h4 class="text-sm font-bold ${successCount === totalFiles ? 'text-green-900' : 'text-blue-900'} mb-1">Upload Complete!</h4>
          <p class="text-xs ${successCount === totalFiles ? 'text-green-800' : 'text-blue-800'}">
            ${successCount} of ${totalFiles} document(s) processed successfully${failCount > 0 ? `, ${failCount} failed` : ''}
          </p>
        </div>
      </div>
    </div>
  `;
  document.getElementById('upload-result').classList.remove('hidden');
  
  // Navigate after upload based on context
  if (successCount > 0) {
    setTimeout(() => {
      closeUploadModal();
      
      if (uploadContext === 'customer_card') {
        // Refresh customer cards view and auto-run reconciliation
        triggerNav('customer_cards');
        triggerDhofarRecon();
      } else if (uploadContext === 'eft') {
        triggerNav('eft_payments');
        triggerDhofarRecon();
      } else {
        const activeNav = document.querySelector('.nav-item.active');
        if (activeNav) triggerNav(activeNav.id.replace('nav-', ''));
      }
    }, 2000);
  } else {
    document.getElementById('upload-btn').disabled = false;
  }
};

// Setup drag and drop
function setupDropZone() {
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  
  if (!dropZone || !fileInput) return;
  
  dropZone.addEventListener('click', () => {
    fileInput.click();
  });
  
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('border-indigo-500', 'bg-indigo-50');
  });
  
  dropZone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dropZone.classList.remove('border-indigo-500', 'bg-indigo-50');
  });
  
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('border-indigo-500', 'bg-indigo-50');
    
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      displaySelectedFiles(files);
    }
  });
}


// ============================================================
// DHOFAR VIEWS
// ============================================================

// --- Customer Cards View ---
async function renderCustomerCards() {
  updateHeader("Customer Cards", "...");
  document.getElementById('search-bar').classList.remove('hidden');
  renderEmptyState("list-content", "Loading customer cards...");

  const bar = document.getElementById('analytics-bar');
  bar.classList.remove('hidden');
  bar.innerHTML = `
    <div class="flex items-center justify-between w-full">
      <div class="flex items-center gap-3">
        <label class="flex items-center gap-2 cursor-pointer text-xs text-gray-600 font-semibold select-none">
          <input type="checkbox" id="select-all-cards" onchange="toggleSelectAll('customer_cards', this.checked)"
            class="w-4 h-4 rounded border-gray-300 text-indigo-600 cursor-pointer">
          Select All
        </label>
        <button id="bulk-delete-cards" onclick="deleteSelected('customer_cards')"
          class="hidden items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold transition-all shadow-sm">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          Delete Selected (<span id="selected-count-cards">0</span>)
        </button>
      </div>
      <button onclick="openUploadModal('customer_card')"
        class="inline-flex items-center gap-2 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold transition-all shadow-sm">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
        </svg>
        Upload Files
      </button>
    </div>
  `;

  const data = await fetchJSON("/api/customer_cards");
  updateHeader("Customer Cards", data.length);
  window.customerCardsData = data;

  if (!data.length) return renderEmptyState("list-content", `
    <div class="p-6 text-center">
      <p class="text-sm text-gray-500 mb-4">No customer cards found.</p>
      <button onclick="openUploadModal('customer_card')" class="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-semibold">
        Upload Files
      </button>
    </div>`);
  renderCustomerCardsList(data);
}

function renderCustomerCardsList(data) {
  const listContent = document.getElementById("list-content");
  listContent.innerHTML = data.map((d, idx) => {
    const card = d.customer_card || {};
    const name = card.customer_name || "Unknown";
    const initial = name.charAt(0).toUpperCase();
    const rows = card.statement_rows || [];
    const totalBal = card.total_balance;

    return `
      <div class="list-item group p-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer border-l-4 border-l-transparent transition-all duration-200" data-index="${idx}" data-id="${d._id}" data-type="customer_cards">
        <div class="flex items-center gap-3 mb-2">
          <input type="checkbox" class="item-checkbox w-4 h-4 rounded border-gray-300 text-indigo-600 cursor-pointer flex-shrink-0"
            data-id="${d._id}" data-type="customer_cards"
            onclick="event.stopPropagation(); updateBulkBar('customer_cards')" />
          <div class="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center text-white font-bold text-sm flex-shrink-0">${initial}</div>
          <div class="flex-1 min-w-0">
            <div class="font-bold text-gray-900 group-hover:text-indigo-600 text-sm truncate">${name}</div>
            <div class="text-[10px] text-gray-500">${card.customer_id || ''}</div>
          </div>
          <button onclick="event.stopPropagation(); deleteRecord('customer_cards','${d._id}')" 
            class="opacity-0 group-hover:opacity-100 p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-all flex-shrink-0" title="Delete">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          </button>
        </div>
        <div class="flex justify-between text-[10px] text-gray-500">
          <span>${rows.length} statement row${rows.length !== 1 ? 's' : ''}</span>
          <span class="font-mono font-bold text-gray-700">${totalBal != null ? 'AED ' + totalBal.toLocaleString() : ''}</span>
        </div>
      </div>
    `;
  }).join("");

  const rows = document.querySelectorAll(".list-item");
  rows.forEach((row, idx) => row.addEventListener("click", () => selectCustomerCard(idx, data)));
  if (data.length > 0) selectCustomerCard(0, data);
}

async function selectCustomerCard(idx, data) {
  document.querySelectorAll(".list-item").forEach(r => r.classList.remove("active"));
  const rows = document.querySelectorAll(".list-item");
  if (rows[idx]) rows[idx].classList.add("active");

  const d = data[idx];
  const card = d.customer_card || {};
  const cardId = d._id;
  const name = card.customer_name || "Unknown";
  const initial = name.charAt(0).toUpperCase();
  const addr = card.address || {};
  const contact = card.contact || {};
  const stmtRows = card.statement_rows || [];

  // Fetch reconciled EFT rows for this card
  let reconRows = [];
  try {
    reconRows = await fetchJSON(`/api/dhofar/reconciliation/card/${cardId}`);
  } catch(e) { /* ignore */ }

  const detailPanel = document.getElementById("detail-panel");

  // Statement rows table
  const stmtHtml = stmtRows.length > 0
    ? buildTable(
        [
          { label: "Posting Date" },
          { label: "Document No." },
          { label: "LPO / Ref" },
          { label: "Customer" },
          { label: "Original Amt", align: "right" },
          { label: "Remaining", align: "right" },
          { label: "Running Total", align: "right" },
        ],
        stmtRows.map(r => `
          <tr class="hover:bg-amber-50 transition-colors">
            <td class="px-4 py-2.5 text-xs text-gray-700 font-mono">${r.posting_date || '-'}</td>
            <td class="px-4 py-2.5 text-xs font-medium text-indigo-700">${r.document_no || '-'}</td>
            <td class="px-4 py-2.5 text-xs text-gray-600 max-w-[120px] truncate" title="${r.lpo || ''}">${r.lpo || '-'}</td>
            <td class="px-4 py-2.5 text-xs text-gray-600 max-w-[120px] truncate">${r.sell_to_customer_name || '-'}</td>
            <td class="px-4 py-2.5 text-xs text-right font-mono ${(r.original_amount || 0) < 0 ? 'text-green-700' : 'text-gray-900'} font-bold">${r.original_amount != null ? r.original_amount.toLocaleString() : '-'}</td>
            <td class="px-4 py-2.5 text-xs text-right font-mono text-gray-700">${r.remaining_amount != null ? r.remaining_amount.toLocaleString() : '-'}</td>
            <td class="px-4 py-2.5 text-xs text-right font-mono font-bold text-gray-900">${r.running_total != null ? r.running_total.toLocaleString() : '-'}</td>
          </tr>
        `).join("")
      )
    : '<p class="text-sm text-gray-400 italic p-4">No statement rows extracted.</p>';

  // Reconciled EFT rows table
  const reconHtml = reconRows.length > 0
    ? buildTable(
        [
          { label: "EFT Date" },
          { label: "Remitter" },
          { label: "EFT Amount", align: "right" },
          { label: "Stmt Doc" },
          { label: "Stmt Amount", align: "right" },
          { label: "Score", align: "right" },
          { label: "Status" },
        ],
        reconRows.map(r => {
          const stmt = r.matched_stmt_row || {};
          const stBadge = r.status === 'matched'
            ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700';
          return `
            <tr class="hover:bg-green-50 transition-colors">
              <td class="px-4 py-2.5 text-xs font-mono text-gray-600">${r.transfer_date || '-'}</td>
              <td class="px-4 py-2.5 text-xs font-medium text-gray-900 max-w-[140px] truncate" title="${r.remitter || ''}">${r.remitter || '-'}</td>
              <td class="px-4 py-2.5 text-xs text-right font-mono font-bold text-gray-900">${r.amount != null ? r.amount.toLocaleString() : '-'}</td>
              <td class="px-4 py-2.5 text-xs text-indigo-700 font-medium">${stmt.document_no || '-'}</td>
              <td class="px-4 py-2.5 text-xs text-right font-mono text-gray-700">${stmt.original_amount != null ? stmt.original_amount.toLocaleString() : '-'}</td>
              <td class="px-4 py-2.5 text-xs text-right font-mono font-bold">${r.total_score}</td>
              <td class="px-4 py-2.5 text-xs">
                <span class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${stBadge}">${r.status}</span>
              </td>
            </tr>
          `;
        }).join("")
      )
    : `<div class="p-6 text-center">
         <p class="text-sm text-gray-400 italic mb-3">No EFT payments reconciled to this card yet.</p>
         <button onclick="triggerDhofarRecon()" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded text-xs font-semibold">Run Reconciliation</button>
       </div>`;

  detailPanel.innerHTML = `
    <!-- Header -->
    <div class="flex justify-between items-start mb-5">
      <div class="flex items-start gap-4">
        <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center text-white font-bold text-2xl shadow-lg">${initial}</div>
        <div>
          <h1 class="text-xl font-bold text-gray-900 mb-0.5">${name}</h1>
          ${card.customer_id ? `<p class="text-xs text-gray-400 font-mono">ID: ${card.customer_id}</p>` : ''}
          ${card.statement_date ? `<p class="text-xs text-gray-400">Statement: ${card.statement_date} · Period: ${card.starting_date || ''} – ${card.ending_date || ''}</p>` : ''}
        </div>
      </div>
      <div class="flex items-center gap-3">
        <div class="text-right">
          <div class="text-lg font-bold text-gray-900">AED ${card.total_balance != null ? card.total_balance.toLocaleString() : '-'}</div>
          ${card.overdue_amount != null ? `<div class="text-xs text-red-600 font-semibold">Overdue: AED ${card.overdue_amount.toLocaleString()}</div>` : ''}
        </div>
        ${buildPDFButton(d.source_file_path)}
      </div>
    </div>

    <!-- Info grid -->
    ${buildMetaGrid([
      { label: "Currency", value: card.currency || "-" },
      { label: "Payment Terms", value: card.payment_terms || "-" },
      { label: "Account Manager", value: card.account_manager || "-" },
      { label: "Statement #", value: card.statement_number || "-" },
    ])}

    ${addr && Object.values(addr).some(v => v) ? `
      <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-5 text-xs text-amber-800">
        📍 ${[addr.street, addr.city, addr.country].filter(Boolean).join(', ')}
      </div>
    ` : ''}

    <!-- Tabs -->
    <div class="border-b border-gray-200 mb-4">
      <div class="flex gap-0">
        <button onclick="switchCardTab('stmt-${cardId}', 'recon-${cardId}', this)" 
          class="card-tab-btn px-5 py-2.5 text-xs font-bold border-b-2 border-indigo-600 text-indigo-700 -mb-px">
          Statement (${stmtRows.length} rows)
        </button>
        <button onclick="switchCardTab('recon-${cardId}', 'stmt-${cardId}', this)"
          class="card-tab-btn px-5 py-2.5 text-xs font-bold border-b-2 border-transparent text-gray-500 hover:text-gray-700 -mb-px">
          Reconciliation (${reconRows.length} matched)
        </button>
      </div>
    </div>

    <!-- Statement tab -->
    <div id="stmt-${cardId}">
      <div class="flex justify-between items-center mb-3">
        <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider">Account Statement</h3>
        <span class="text-xs text-gray-400">${stmtRows.length} rows · Balance: AED ${card.total_balance != null ? card.total_balance.toLocaleString() : '-'}</span>
      </div>
      ${stmtHtml}
    </div>

    <!-- Reconciliation tab (hidden by default) -->
    <div id="recon-${cardId}" class="hidden">
      <div class="flex justify-between items-center mb-3">
        <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider">EFT Payments Matched to This Card</h3>
        <span class="text-xs text-gray-400">${reconRows.length} accepted · AED ${reconRows.reduce((s,r) => s + (r.amount||0), 0).toLocaleString()}</span>
      </div>
      ${reconHtml}
    </div>
  `;
}

window.switchCardTab = (showId, hideId, btn) => {
  document.getElementById(showId).classList.remove('hidden');
  document.getElementById(hideId).classList.add('hidden');
  document.querySelectorAll('.card-tab-btn').forEach(b => {
    b.classList.remove('border-indigo-600', 'text-indigo-700');
    b.classList.add('border-transparent', 'text-gray-500');
  });
  btn.classList.remove('border-transparent', 'text-gray-500');
  btn.classList.add('border-indigo-600', 'text-indigo-700');
};

function filterCustomerCards(term) {
  if (!window.customerCardsData) return;
  const filtered = term
    ? window.customerCardsData.filter(d => {
        const card = d.customer_card || {};
        return (
          (card.customer_name || '').toLowerCase().includes(term) ||
          (card.customer_id || '').toLowerCase().includes(term) ||
          (card.trade_name || '').toLowerCase().includes(term) ||
          (card.industry || '').toLowerCase().includes(term)
        );
      })
    : window.customerCardsData;
  renderCustomerCardsList(filtered);
}

// --- EFT Payments View ---
async function renderEFTPayments() {
  updateHeader("EFT Payments", "...");
  document.getElementById('search-bar').classList.remove('hidden');
  renderEmptyState("list-content", "Loading EFT payments...");

  const bar = document.getElementById('analytics-bar');
  bar.classList.remove('hidden');
  bar.innerHTML = `
    <div class="flex items-center justify-between w-full">
      <div class="flex items-center gap-3">
        <label class="flex items-center gap-2 cursor-pointer text-xs text-gray-600 font-semibold select-none">
          <input type="checkbox" id="select-all-eft" onchange="toggleSelectAll('eft_payments', this.checked)"
            class="w-4 h-4 rounded border-gray-300 text-indigo-600 cursor-pointer">
          Select All
        </label>
        <button id="bulk-delete-eft" onclick="deleteSelected('eft_payments')"
          class="hidden items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold transition-all shadow-sm">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          Delete Selected (<span id="selected-count-eft">0</span>)
        </button>
      </div>
      <button onclick="openUploadModal('eft')"
        class="inline-flex items-center gap-2 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold transition-all shadow-sm">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
        </svg>
        Upload Files
      </button>
    </div>
  `;

  const data = await fetchJSON("/api/eft_payments");
  updateHeader("EFT Payments", data.length);
  window.eftPaymentsData = data;

  if (!data.length) return renderEmptyState("list-content", "No EFT payments found. Run ingest_dhofar.py to import.");

  renderEFTPaymentsList(data);
}

function renderEFTPaymentsList(data) {
  const listContent = document.getElementById("list-content");
  listContent.innerHTML = data.map((d, idx) => {
    const eft = d.eft_payment || {};
    const ref = eft.eft_reference || d.source_filename || "Unknown";
    const total = eft.total_amount;
    const currency = eft.currency || "AED";
    const itemCount = (eft.items || []).length;

    return `
      <div class="list-item group p-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer border-l-4 border-l-transparent transition-all duration-200" data-index="${idx}" data-id="${d._id}" data-type="eft_payments">
        <div class="flex justify-between items-start mb-2">
          <div class="flex items-center gap-2 flex-1 min-w-0">
            <input type="checkbox" class="item-checkbox w-4 h-4 rounded border-gray-300 text-indigo-600 cursor-pointer flex-shrink-0"
              data-id="${d._id}" data-type="eft_payments"
              onclick="event.stopPropagation(); updateBulkBar('eft_payments')" />
            <span class="font-bold text-gray-900 group-hover:text-indigo-600 text-sm truncate">${ref}</span>
          </div>
          <div class="flex items-center gap-1 ml-2 flex-shrink-0">
            ${total ? `<span class="text-xs font-mono font-bold text-gray-700">${currency} ${total.toLocaleString()}</span>` : ''}
            <button onclick="event.stopPropagation(); deleteRecord('eft_payments','${d._id}')"
              class="opacity-0 group-hover:opacity-100 p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-all" title="Delete">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
            </button>
          </div>
        </div>
        <div class="flex justify-between text-[10px] text-gray-500">
          <span>${eft.payment_date || ''}</span>
          <span>${itemCount} payment${itemCount !== 1 ? 's' : ''}</span>
        </div>
      </div>
    `;
  }).join("");

  const rows = document.querySelectorAll(".list-item");
  const select = (idx) => {
    rows.forEach(r => r.classList.remove("active"));
    rows[idx].classList.add("active");

    const d = data[idx];
    const eft = d.eft_payment || {};
    const detailPanel = document.getElementById("detail-panel");
    const currency = eft.currency || "AED";
    const items = eft.items || [];

    const itemsHtml = items.map(item => `
      <tr>
        <td class="px-4 py-3 text-xs font-medium text-gray-900">${item.beneficiary_name || '-'}</td>
        <td class="px-4 py-3 text-xs text-gray-600">${item.bank_name || '-'}</td>
        <td class="px-4 py-3 text-xs text-gray-500 max-w-xs truncate" title="${(item.description || item.remarks || '').replace(/"/g, '&quot;')}">${item.description || item.remarks || '-'}</td>
        <td class="px-4 py-3 text-xs text-right font-mono font-bold text-gray-900">${item.amount ? item.amount.toLocaleString() : '-'}</td>
        <td class="px-4 py-3 text-xs text-gray-500">${item.transfer_date || item.reference || '-'}</td>
      </tr>
    `).join("");

    detailPanel.innerHTML = `
      <div class="flex justify-between items-start mb-6">
        <div class="flex items-start gap-4">
          <div class="w-16 h-16 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-white shadow-lg">
            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"></path>
            </svg>
          </div>
          <div>
            <h1 class="text-2xl font-bold text-gray-900 mb-1">${eft.eft_reference || d.source_filename || "EFT Payment"}</h1>
            ${eft.payer_name ? `<p class="text-sm text-gray-500">Payer: ${eft.payer_name}</p>` : ''}
            ${eft.bank_name ? `<p class="text-xs text-gray-400 mt-1">Bank: ${eft.bank_name}</p>` : ''}
          </div>
        </div>
      </div>

      ${buildMetaGrid([
        { label: "Payment Date", value: eft.payment_date || "-" },
        { label: "Currency", value: currency },
        { label: "Total Amount", value: eft.total_amount ? `${currency} ${eft.total_amount.toLocaleString()}` : "-" },
        { label: "Payments", value: items.length },
      ])}

      ${items.length > 0 ? `
        <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Payment Details</h3>
        ${buildTable(
          [
            { label: "Beneficiary" },
            { label: "Bank" },
            { label: "Description / Narration" },
            { label: "Amount (AED)", align: "right" },
            { label: "Date / Ref" },
          ],
          itemsHtml
        )}

        <div class="flex justify-end mb-6">
          <div class="w-72 bg-white rounded-lg border border-gray-200 p-4 shadow-md">
            <div class="flex justify-between text-base font-bold text-gray-900 pt-2">
              <span>Total</span>
              <span class="font-mono">${currency} ${eft.total_amount ? eft.total_amount.toLocaleString() : '-'}</span>
            </div>
          </div>
        </div>
      ` : '<p class="text-sm text-gray-400 italic">No payment line items found.</p>'}

      ${eft.notes ? `
        <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <h3 class="text-xs font-bold text-yellow-900 uppercase tracking-wider mb-2">Notes</h3>
          <p class="text-sm text-yellow-800">${eft.notes}</p>
        </div>
      ` : ''}
    `;
  };

  rows.forEach((row, idx) => row.addEventListener("click", () => select(idx)));
  if (data.length > 0) select(0);
}

function filterEFTPayments(term) {
  if (!window.eftPaymentsData) return;
  const filtered = term
    ? window.eftPaymentsData.filter(d => {
        const eft = d.eft_payment || {};
        return (
          (eft.eft_reference || '').toLowerCase().includes(term) ||
          (d.source_filename || '').toLowerCase().includes(term) ||
          (eft.payment_date || '').toLowerCase().includes(term) ||
          (eft.payer_name || '').toLowerCase().includes(term)
        );
      })
    : window.eftPaymentsData;
  renderEFTPaymentsList(filtered);
}


// ============================================================
// DHOFAR EFT RECONCILIATION VIEW  (5-pass engine)
// ============================================================

async function renderDhofarReconciliation() {
  updateHeader("EFT Reconciliation", "...");
  document.getElementById('search-bar').classList.remove('hidden');
  renderEmptyState("list-content", "Loading...");

  const data = await fetchJSON("/api/dhofar/reconciliation");
  window.dhofarReconData = data;

  const matched   = data.matched   || [];
  const unmatchedB = data.unmatched_bank || [];
  const unmatchedI = data.unmatched_invoices || [];
  const total = matched.length + unmatchedB.length;

  updateHeader("EFT Reconciliation", total);

  if (!total && !unmatchedI.length) {
    document.getElementById("list-content").innerHTML = `
      <div class="p-6 text-center">
        <p class="text-sm text-gray-500 mb-4">No reconciliation data yet.</p>
        <button onclick="triggerDhofarRecon()" class="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-semibold">
          Run Reconciliation
        </button>
      </div>`;
    return;
  }

  // Build flat array for renderDhofarReconSummary (expects {status, amount, matched_amount})
  const flatData = [
    ...matched.map(r => {
      const row = r.bank_row || {};
      const isPartial = row.match_method === 'pass4_partial' || (row.unallocated_amount || 0) > 0.05;
      return {
        status: isPartial ? 'partial' : 'matched',
        amount: row.matched_amount || row.amount || 0,
        total_amount: row.amount || 0,
      };
    }),
    ...unmatchedB.map(r => ({ status: 'unmatched', amount: r.amount || 0, total_amount: r.amount || 0 })),
  ];
  renderDhofarReconSummary(flatData);
  renderDhofarReconTabs(matched, unmatchedB, unmatchedI);
}

function renderDhofarReconSummary(matched, unmatchedB, unmatchedI) {
  const matchedAmt  = matched.reduce((s, r) => s + (r.bank_row?.matched_amount || 0), 0);
  const unmatchedAmt = unmatchedB.reduce((s, r) => s + (r.unallocated_amount || 0), 0);
  const openInvAmt  = unmatchedI.reduce((s, r) => s + (r.remaining_amount || 0), 0);
  const total = matched.length + unmatchedB.length;
  const pct = total > 0 ? Math.round(matched.length / total * 100) : 0;

  const bar = document.getElementById('analytics-bar');
  bar.classList.remove('hidden');
  bar.innerHTML = `
    <div class="flex items-center justify-between gap-4 flex-wrap w-full">
      <div class="flex items-center gap-5">
        <div class="text-center">
          <div class="text-xl font-bold text-green-600">${matched.length}</div>
          <div class="text-[7.5px] text-gray-500 uppercase font-semibold mt-1">Matched Bank</div>
        </div>
        <div class="text-center">
          <div class="text-xl font-bold text-red-500">${unmatchedB.length}</div>
          <div class="text-[7.5px] text-gray-500 uppercase font-semibold mt-1">Unmatched Bank</div>
        </div>
        <div class="text-center">
          <div class="text-xl font-bold text-amber-600">${unmatchedI.length}</div>
          <div class="text-[7.5px] text-gray-500 uppercase font-semibold mt-1">Open Invoices</div>
        </div>
        <div class="h-10 w-px bg-gray-300"></div>
        <div class="text-center">
          <div class="text-xl font-bold text-indigo-600">${pct}%</div>
          <div class="text-[7.5px] text-gray-500 uppercase font-semibold mt-1">Match Rate</div>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <div class="px-3 py-2 bg-green-600 rounded-lg shadow-sm text-center min-w-[100px]">
          <div class="text-sm font-bold text-white">AED ${matchedAmt.toLocaleString(undefined,{maximumFractionDigits:0})}</div>
          <div class="text-[8px] text-green-100 uppercase font-bold mt-0.5">Matched</div>
        </div>
        <div class="px-3 py-2 bg-red-500 rounded-lg shadow-sm text-center min-w-[100px]">
          <div class="text-sm font-bold text-white">AED ${unmatchedAmt.toLocaleString(undefined,{maximumFractionDigits:0})}</div>
          <div class="text-[8px] text-red-100 uppercase font-bold mt-0.5">Unmatched</div>
        </div>
        <div class="px-3 py-2 bg-amber-600 rounded-lg shadow-sm text-center min-w-[100px]">
          <div class="text-sm font-bold text-white">AED ${openInvAmt.toLocaleString(undefined,{maximumFractionDigits:0})}</div>
          <div class="text-[8px] text-amber-100 uppercase font-bold mt-0.5">Open Invoices</div>
        </div>
        <button onclick="triggerDhofarRecon()" class="px-3 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-sm">↻ Re-run</button>
      </div>
    </div>`;
}

function renderDhofarReconTabs(matched, unmatchedB, unmatchedI) {
  const listContent = document.getElementById("list-content");

  const tabBar = `
    <div class="border-b border-gray-200 bg-white sticky top-0 z-10">
      <div class="flex">
        <button onclick="switchReconTab('tab-matched','tab-unbank','tab-uninv',this)"
          class="recon-tab flex-1 py-2.5 text-[10px] font-bold border-b-2 border-green-600 text-green-700 -mb-px">
          ✓ Matched (${matched.length})
        </button>
        <button onclick="switchReconTab('tab-unbank','tab-matched','tab-uninv',this)"
          class="recon-tab flex-1 py-2.5 text-[10px] font-bold border-b-2 border-transparent text-gray-500 hover:text-gray-700 -mb-px">
          ✗ Bank (${unmatchedB.length})
        </button>
        <button onclick="switchReconTab('tab-uninv','tab-matched','tab-unbank',this)"
          class="recon-tab flex-1 py-2.5 text-[10px] font-bold border-b-2 border-transparent text-gray-500 hover:text-gray-700 -mb-px">
          📄 Invoices (${unmatchedI.length})
        </button>
      </div>
      <!-- Bulk action bar for recon tabs -->
      <div class="flex items-center gap-3 px-3 py-2 bg-gray-50 border-t border-gray-100">
        <label class="flex items-center gap-2 cursor-pointer text-[10px] text-gray-600 font-semibold select-none">
          <input type="checkbox" id="select-all-recon" onchange="toggleSelectAllRecon(this.checked)"
            class="w-3.5 h-3.5 rounded border-gray-300 text-indigo-600 cursor-pointer">
          Select All
        </label>
        <button id="bulk-delete-recon" onclick="deleteSelectedRecon()"
          class="hidden items-center gap-1 px-2.5 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-[10px] font-semibold transition-all">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          Delete (<span id="selected-count-recon">0</span>)
        </button>
      </div>
    </div>
    <div id="tab-matched" class="overflow-y-auto">${_buildMatchedList(matched)}</div>
    <div id="tab-unbank"  class="hidden overflow-y-auto">${_buildUnmatchedBankList(unmatchedB)}</div>
    <div id="tab-uninv"   class="hidden overflow-y-auto">${_buildUnmatchedInvList(unmatchedI)}</div>`;

  listContent.innerHTML = tabBar;

  // Click handlers for matched rows
  listContent.querySelectorAll('.recon-matched-row').forEach((el, idx) => {
    el.addEventListener('click', () => selectMatchedRow(idx, matched));
  });
  listContent.querySelectorAll('.recon-unbank-row').forEach((el, idx) => {
    el.addEventListener('click', () => selectUnmatchedBank(idx, unmatchedB));
  });
  listContent.querySelectorAll('.recon-uninv-row').forEach((el, idx) => {
    el.addEventListener('click', () => selectUnmatchedInv(idx, unmatchedI));
  });

  if (matched.length > 0) selectMatchedRow(0, matched);
}

window.switchReconTab = (showId, hide1, hide2, btn) => {
  ['tab-matched','tab-unbank','tab-uninv'].forEach(id => {
    document.getElementById(id)?.classList.add('hidden');
  });
  document.getElementById(showId)?.classList.remove('hidden');
  document.querySelectorAll('.recon-tab').forEach(b => {
    b.classList.remove('border-green-600','text-green-700','border-red-500','text-red-600','border-amber-600','text-amber-700');
    b.classList.add('border-transparent','text-gray-500');
  });
  const colors = {
    'tab-matched': ['border-green-600','text-green-700'],
    'tab-unbank':  ['border-red-500','text-red-600'],
    'tab-uninv':   ['border-amber-600','text-amber-700'],
  };
  const c = colors[showId] || ['border-indigo-600','text-indigo-700'];
  btn.classList.remove('border-transparent','text-gray-500');
  btn.classList.add(...c);
};

function _methodBadge(method) {
  const labels = {
    pass1_doc_no: { label: 'Doc#', cls: 'bg-green-100 text-green-700' },
    pass2_name_exact: { label: 'Name+Amt', cls: 'bg-blue-100 text-blue-700' },
    pass3_combo: { label: 'Combo', cls: 'bg-purple-100 text-purple-700' },
    pass4_partial: { label: 'Partial', cls: 'bg-amber-100 text-amber-700' },
    pass5_processor: { label: 'Processor', cls: 'bg-gray-100 text-gray-600' },
  };
  const m = labels[method] || { label: method || '?', cls: 'bg-gray-100 text-gray-600' };
  return `<span class="text-[9px] font-bold px-1.5 py-0.5 rounded ${m.cls}">${m.label}</span>`;
}

function _buildMatchedList(matched) {
  if (!matched.length) return '<p class="p-4 text-xs text-gray-400 italic text-center">No matched rows yet.</p>';
  return matched.map((r, idx) => {
    const row = r.bank_row || {};
    const docs = (row.matched_doc_nos || []).join(', ');
    return `
      <div class="recon-matched-row group p-3 border-b border-gray-100 hover:bg-green-50 cursor-pointer border-l-4 border-l-green-500 transition-all">
        <div class="flex justify-between items-start mb-1">
          <div class="flex items-center gap-2 flex-1 min-w-0">
            <input type="checkbox" class="recon-checkbox w-3.5 h-3.5 rounded border-gray-300 text-indigo-600 cursor-pointer flex-shrink-0"
              data-id="${row._id}" data-type="recon_bank"
              onclick="event.stopPropagation(); updateReconBulkBar()" />
            <span class="text-xs font-bold text-gray-900 truncate">${row.remitter_name || '-'}</span>
          </div>
          <div class="flex items-center gap-1 ml-2 flex-shrink-0">
            <span class="text-xs font-mono font-bold text-gray-800">AED ${(row.amount||0).toLocaleString()}</span>
            <button onclick="event.stopPropagation(); deleteRecord('recon_bank','${row._id}')"
              class="opacity-0 group-hover:opacity-100 p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-all" title="Delete">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
            </button>
          </div>
        </div>
        <div class="flex justify-between items-center">
          <span class="text-[10px] text-indigo-600 truncate flex-1">${docs || row.matched_customer || '-'}</span>
          ${_methodBadge(row.match_method)}
        </div>
      </div>`;
  }).join('');
}

function _buildUnmatchedBankList(rows) {
  if (!rows.length) return '<p class="p-4 text-xs text-gray-400 italic text-center">All bank rows matched.</p>';
  return rows.map((r, idx) => `
    <div class="recon-unbank-row group p-3 border-b border-gray-100 hover:bg-red-50 cursor-pointer border-l-4 border-l-red-400 transition-all">
      <div class="flex justify-between items-start mb-1">
        <div class="flex items-center gap-2 flex-1 min-w-0">
          <input type="checkbox" class="recon-checkbox w-3.5 h-3.5 rounded border-gray-300 text-indigo-600 cursor-pointer flex-shrink-0"
            data-id="${r._id}" data-type="recon_bank"
            onclick="event.stopPropagation(); updateReconBulkBar()" />
          <span class="text-xs font-bold text-gray-900 truncate">${r.remitter_name || '-'}</span>
        </div>
        <div class="flex items-center gap-1 ml-2 flex-shrink-0">
          <span class="text-xs font-mono font-bold text-red-700">AED ${(r.unallocated_amount||0).toLocaleString()}</span>
          <button onclick="event.stopPropagation(); deleteRecord('recon_bank','${r._id}')"
            class="opacity-0 group-hover:opacity-100 p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-all" title="Delete">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          </button>
        </div>
      </div>
      <div class="text-[10px] text-gray-500">${r.txn_date || ''} · ${r.bank_name || ''}</div>
    </div>`).join('');
}

function _buildUnmatchedInvList(rows) {
  if (!rows.length) return '<p class="p-4 text-xs text-gray-400 italic text-center">All invoices cleared.</p>';
  return rows.map((r, idx) => `
    <div class="recon-uninv-row group p-3 border-b border-gray-100 hover:bg-amber-50 cursor-pointer border-l-4 border-l-amber-500 transition-all">
      <div class="flex justify-between items-start mb-1">
        <div class="flex items-center gap-2 flex-1 min-w-0">
          <input type="checkbox" class="recon-checkbox w-3.5 h-3.5 rounded border-gray-300 text-indigo-600 cursor-pointer flex-shrink-0"
            data-id="${r._id}" data-type="recon_invoice"
            onclick="event.stopPropagation(); updateReconBulkBar()" />
          <span class="text-xs font-bold text-gray-900 truncate">${r.customer_name || '-'}</span>
        </div>
        <div class="flex items-center gap-1 ml-2 flex-shrink-0">
          <span class="text-xs font-mono font-bold text-amber-700">AED ${(r.remaining_amount||0).toLocaleString()}</span>
          <button onclick="event.stopPropagation(); deleteRecord('recon_invoice','${r._id}')"
            class="opacity-0 group-hover:opacity-100 p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-all" title="Delete">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          </button>
        </div>
      </div>
      <div class="text-[10px] text-gray-500">${r.doc_no || '-'} · ${r.posting_date || ''}</div>
    </div>`).join('');
}

function selectMatchedRow(idx, matched) {
  document.querySelectorAll('.recon-matched-row').forEach(r => r.classList.remove('active'));
  const rows = document.querySelectorAll('.recon-matched-row');
  if (rows[idx]) rows[idx].classList.add('active');

  const r = matched[idx];
  const row = r.bank_row || {};
  const invoices = r.invoices || [];
  const pairs = r.pairs || [];

  const invRows = invoices.map(inv => `
    <tr>
      <td class="px-3 py-2 text-xs font-medium text-indigo-700">${inv.doc_no || '-'}</td>
      <td class="px-3 py-2 text-xs text-gray-600">${inv.customer_name || '-'}</td>
      <td class="px-3 py-2 text-xs font-mono text-gray-600">${inv.posting_date || '-'}</td>
      <td class="px-3 py-2 text-xs text-right font-mono">${(inv.original_amount||0).toLocaleString()}</td>
      <td class="px-3 py-2 text-xs text-right font-mono ${inv.cleared_flag ? 'text-green-700 font-bold' : 'text-amber-700'}">${(inv.remaining_amount||0).toLocaleString()}</td>
      <td class="px-3 py-2 text-xs text-center">${inv.cleared_flag ? '✓' : '~'}</td>
    </tr>`).join('');

  document.getElementById('detail-panel').innerHTML = `
    <div class="mb-4 flex items-start justify-between">
      <div>
        <h1 class="text-lg font-bold text-gray-900 mb-1">${row.remitter_name || 'Unknown'}</h1>
        <div class="flex items-center gap-2">
          <span class="text-xs text-gray-500">${row.txn_date || ''} · ${row.bank_name || ''}</span>
          ${_methodBadge(row.match_method)}
        </div>
      </div>
      <div class="text-right">
        <div class="text-2xl font-bold text-gray-900">AED ${(row.amount||0).toLocaleString()}</div>
        <div class="text-xs text-green-600 font-semibold">Matched: AED ${(row.matched_amount||0).toLocaleString()}</div>
        ${(row.unallocated_amount||0) > 0.05 ? `<div class="text-xs text-amber-600">Unallocated: AED ${(row.unallocated_amount||0).toLocaleString()}</div>` : ''}
      </div>
    </div>

    ${buildMetaGrid([
      { label: "Matched Customer", value: row.matched_customer || "-" },
      { label: "Matched Docs", value: (row.matched_doc_nos||[]).join(', ') || "-" },
      { label: "Match Method", value: row.match_method || "-" },
      { label: "Value Date", value: row.value_date || "-" },
    ])}

    <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Linked Invoices</h3>
    ${buildTable(
      [{label:'Doc No'},{label:'Customer'},{label:'Posting Date'},{label:'Original',align:'right'},{label:'Remaining',align:'right'},{label:'Cleared',align:'right'}],
      invRows || '<tr><td colspan="6" class="px-3 py-4 text-xs text-gray-400 text-center italic">No invoices linked</td></tr>'
    )}

    <div class="bg-gray-50 border border-gray-200 rounded-lg p-3 mt-4">
      <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Raw Description</h3>
      <p class="text-xs text-gray-700 font-mono leading-relaxed break-all">${row.raw_description || '-'}</p>
    </div>`;
}

function selectUnmatchedBank(idx, rows) {
  document.querySelectorAll('.recon-unbank-row').forEach(r => r.classList.remove('active'));
  const els = document.querySelectorAll('.recon-unbank-row');
  if (els[idx]) els[idx].classList.add('active');

  const r = rows[idx];
  document.getElementById('detail-panel').innerHTML = `
    <div class="mb-4 flex items-start justify-between">
      <div>
        <h1 class="text-lg font-bold text-gray-900 mb-1">${r.remitter_name || 'Unknown'}</h1>
        <span class="text-xs text-gray-500">${r.txn_date || ''} · ${r.bank_name || ''}</span>
      </div>
      <div class="text-right">
        <div class="text-2xl font-bold text-red-600">AED ${(r.unallocated_amount||0).toLocaleString()}</div>
        <div class="text-xs text-gray-500">Unallocated</div>
      </div>
    </div>
    ${buildMetaGrid([
      { label: "Amount", value: `AED ${(r.amount||0).toLocaleString()}` },
      { label: "Currency", value: r.currency || "AED" },
      { label: "Candidate Docs", value: (r.candidate_doc_nos||[]).join(', ') || "None found" },
      { label: "Is Processor", value: r.is_processor ? "Yes" : "No" },
    ])}
    <div class="bg-red-50 border border-red-200 rounded-lg p-3 mt-2">
      <h3 class="text-xs font-bold text-red-700 uppercase tracking-wider mb-2">Needs Manual Review</h3>
      <p class="text-xs text-gray-700 font-mono leading-relaxed break-all">${r.raw_description || '-'}</p>
    </div>`;
}

function selectUnmatchedInv(idx, rows) {
  document.querySelectorAll('.recon-uninv-row').forEach(r => r.classList.remove('active'));
  const els = document.querySelectorAll('.recon-uninv-row');
  if (els[idx]) els[idx].classList.add('active');

  const r = rows[idx];
  document.getElementById('detail-panel').innerHTML = `
    <div class="mb-4 flex items-start justify-between">
      <div>
        <h1 class="text-lg font-bold text-gray-900 mb-1">${r.customer_name || 'Unknown'}</h1>
        <span class="text-xs text-gray-500">${r.doc_no || ''} · ${r.posting_date || ''}</span>
      </div>
      <div class="text-right">
        <div class="text-2xl font-bold text-amber-600">AED ${(r.remaining_amount||0).toLocaleString()}</div>
        <div class="text-xs text-gray-500">Outstanding</div>
      </div>
    </div>
    ${buildMetaGrid([
      { label: "Document No.", value: r.doc_no || "-" },
      { label: "Original Amount", value: `AED ${(r.original_amount||0).toLocaleString()}` },
      { label: "Remaining", value: `AED ${(r.remaining_amount||0).toLocaleString()}` },
      { label: "LPO", value: r.lpo || "-" },
    ])}
    <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 mt-2">
      <p class="text-xs text-amber-800">This invoice has not been matched to any bank payment. It may be unpaid or paid via a channel not in the current bank statement.</p>
    </div>`;
}

// --- Bulk Selection Helpers ---

// Update the "Delete Selected" button visibility for customer_cards / eft_payments
window.updateBulkBar = (type) => {
  const suffixMap = { customer_cards: 'cards', eft_payments: 'eft' };
  const suffix = suffixMap[type];
  const checked = document.querySelectorAll(`.item-checkbox[data-type="${type}"]:checked`);
  const btn = document.getElementById(`bulk-delete-${suffix}`);
  const countEl = document.getElementById(`selected-count-${suffix}`);
  if (!btn) return;
  if (checked.length > 0) {
    btn.classList.remove('hidden');
    btn.classList.add('inline-flex');
  } else {
    btn.classList.add('hidden');
    btn.classList.remove('inline-flex');
  }
  if (countEl) countEl.textContent = checked.length;
};

window.toggleSelectAll = (type, checked) => {
  document.querySelectorAll(`.item-checkbox[data-type="${type}"]`).forEach(cb => cb.checked = checked);
  updateBulkBar(type);
};

window.deleteSelected = async (type) => {
  const checked = [...document.querySelectorAll(`.item-checkbox[data-type="${type}"]:checked`)];
  if (!checked.length) return;
  if (!confirm(`Delete ${checked.length} selected record(s)? This cannot be undone.`)) return;
  let failed = 0;
  for (const cb of checked) {
    try {
      const res = await fetch(`/api/${type}/${cb.dataset.id}`, { method: 'DELETE' });
      if (!res.ok) failed++;
    } catch { failed++; }
  }
  showToast(failed ? `Deleted with ${failed} error(s)` : `Deleted ${checked.length} record(s)`, failed ? 'error' : 'success');
  const activeNav = document.querySelector('.nav-item.active');
  if (activeNav) triggerNav(activeNav.id.replace('nav-', ''));
};

// Recon tab bulk helpers
window.updateReconBulkBar = () => {
  const checked = document.querySelectorAll('.recon-checkbox:checked');
  const btn = document.getElementById('bulk-delete-recon');
  const countEl = document.getElementById('selected-count-recon');
  if (!btn) return;
  if (checked.length > 0) {
    btn.classList.remove('hidden');
    btn.classList.add('inline-flex');
  } else {
    btn.classList.add('hidden');
    btn.classList.remove('inline-flex');
  }
  if (countEl) countEl.textContent = checked.length;
};

window.toggleSelectAllRecon = (checked) => {
  document.querySelectorAll('.recon-checkbox').forEach(cb => cb.checked = checked);
  updateReconBulkBar();
};

window.deleteSelectedRecon = async () => {
  const checked = [...document.querySelectorAll('.recon-checkbox:checked')];
  if (!checked.length) return;
  if (!confirm(`Delete ${checked.length} selected record(s)? This cannot be undone.`)) return;
  let failed = 0;
  for (const cb of checked) {
    const urlMap = { recon_bank: `/api/recon/bank/${cb.dataset.id}`, recon_invoice: `/api/recon/invoice/${cb.dataset.id}` };
    try {
      const res = await fetch(urlMap[cb.dataset.type], { method: 'DELETE' });
      if (!res.ok) failed++;
    } catch { failed++; }
  }
  showToast(failed ? `Deleted with ${failed} error(s)` : `Deleted ${checked.length} record(s)`, failed ? 'error' : 'success');
  renderDhofarReconciliation();
};

// --- Delete Record Handler ---
window.deleteRecord = async (type, id) => {
  const labels = {
    customer_cards: 'customer card',
    eft_payments: 'EFT payment',
    recon_bank: 'bank transaction',
    recon_invoice: 'open invoice',
  };
  if (!confirm(`Delete this ${labels[type] || 'record'}? This cannot be undone.`)) return;

  const urlMap = {
    customer_cards: `/api/customer_cards/${id}`,
    eft_payments: `/api/eft_payments/${id}`,
    recon_bank: `/api/recon/bank/${id}`,
    recon_invoice: `/api/recon/invoice/${id}`,
  };

  try {
    const res = await fetch(urlMap[type], { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast(`Deleted successfully`, 'success');
    // Refresh the current view
    const activeNav = document.querySelector('.nav-item.active');
    if (activeNav) triggerNav(activeNav.id.replace('nav-', ''));
  } catch (e) {
    showToast(`Delete failed: ${e.message}`, 'error');
  }
};

window.triggerDhofarRecon = async () => {
  showToast('Running reconciliation engine...', 'success');
  try {
    const res = await fetch('/api/dhofar/reconcile', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      const s = data.summary;
      showToast(`Done: ${s.bank_rows_matched} bank matched, ${s.invoices_cleared} invoices cleared`, 'success');
      renderDhofarReconciliation();
    } else {
      showToast('Failed: ' + (data.detail || 'unknown error'), 'error');
    }
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
};

function filterDhofarRecon(term) {
  if (!window.dhofarReconData) return;
  const data = window.dhofarReconData;
  if (!term) { renderDhofarReconTabs(data.matched||[], data.unmatched_bank||[], data.unmatched_invoices||[]); return; }
  const t = term.toLowerCase();
  const matched   = (data.matched||[]).filter(r => {
    const row = r.bank_row || {};
    return (row.remitter_name||'').toLowerCase().includes(t) ||
           (row.matched_customer||'').toLowerCase().includes(t) ||
           (row.matched_doc_nos||[]).join(' ').toLowerCase().includes(t);
  });
  const unmatchedB = (data.unmatched_bank||[]).filter(r =>
    (r.remitter_name||'').toLowerCase().includes(t) || (r.raw_description||'').toLowerCase().includes(t));
  const unmatchedI = (data.unmatched_invoices||[]).filter(r =>
    (r.customer_name||'').toLowerCase().includes(t) || (r.doc_no||'').toLowerCase().includes(t));
  renderDhofarReconTabs(matched, unmatchedB, unmatchedI);
}


function renderDhofarReconList(data) {
  const statusStyles = {
    matched:   { bg: 'bg-green-50',  border: 'border-l-green-500',  badge: 'bg-green-100 text-green-700',  label: 'MATCHED'   },
    partial:   { bg: 'bg-amber-50',  border: 'border-l-amber-500',  badge: 'bg-amber-100 text-amber-700',  label: 'PARTIAL'   },
    unmatched: { bg: 'bg-gray-50',   border: 'border-l-gray-400',   badge: 'bg-gray-100 text-gray-600',    label: 'UNMATCHED' },
  };

  const listContent = document.getElementById("list-content");
  listContent.innerHTML = data.map((d, idx) => {
    const st = statusStyles[d.status] || statusStyles.unmatched;
    const card = d.matched_card || d.best_candidate || {};
    const remitter = d.remitter || '-';
    const amount = d.amount;

    return `
      <div class="list-item group p-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer border-l-4 ${st.border} transition-all duration-200" data-index="${idx}">
        <div class="flex justify-between items-start mb-1.5">
          <span class="font-bold text-gray-900 group-hover:text-indigo-600 text-sm truncate flex-1 mr-2">${remitter}</span>
          <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${st.badge} flex-shrink-0">${st.label}</span>
        </div>
        <div class="flex justify-between items-end">
          <div class="text-[10px] text-gray-500 truncate flex-1">
            ${card.customer_name ? `→ ${card.customer_name}` : '<span class="italic">No match</span>'}
          </div>
          <div class="text-right ml-2 flex-shrink-0">
            <div class="text-xs font-mono font-bold text-gray-800">AED ${amount ? amount.toLocaleString() : '-'}</div>
            <div class="text-[9px] text-gray-400">score: ${d.total_score}</div>
          </div>
        </div>
      </div>
    `;
  }).join("");

  const rows = document.querySelectorAll(".list-item");
  rows.forEach((row, idx) => row.addEventListener("click", () => selectDhofarRecon(idx, data)));
  if (data.length > 0) selectDhofarRecon(0, data);
}

function selectDhofarRecon(idx, data) {
  document.querySelectorAll(".list-item").forEach(r => r.classList.remove("active"));
  const rows = document.querySelectorAll(".list-item");
  if (rows[idx]) rows[idx].classList.add("active");

  const d = data[idx];
  const card = d.matched_card || d.best_candidate || {};
  const detailPanel = document.getElementById("detail-panel");

  const statusColors = {
    matched:   'bg-green-100 text-green-800 ring-green-600/20',
    partial:   'bg-amber-100 text-amber-800 ring-amber-600/20',
    unmatched: 'bg-gray-100 text-gray-700 ring-gray-600/20',
  };
  const statusBadgeClass = statusColors[d.status] || statusColors.unmatched;

  // Score bar
  const scoreBar = (score, max, color) => {
    const pct = Math.min(100, (score / max) * 100);
    return `
      <div class="flex items-center gap-2">
        <div class="flex-1 bg-gray-200 rounded-full h-2">
          <div class="h-2 rounded-full ${color}" style="width:${pct}%"></div>
        </div>
        <span class="text-xs font-mono w-8 text-right">${score}</span>
      </div>`;
  };

  // Candidates table
  const candidatesHtml = (d.all_candidates || []).map((c, i) => `
    <tr class="${i === 0 && d.status !== 'unmatched' ? 'bg-green-50' : ''}">
      <td class="px-3 py-2 text-xs font-medium text-gray-900">${c.customer_name || '-'}</td>
      <td class="px-3 py-2 text-xs text-gray-600">${c.customer_id || '-'}</td>
      <td class="px-3 py-2 text-xs text-right font-mono">${c.name_score}</td>
      <td class="px-3 py-2 text-xs text-right font-mono">${c.amount_score}</td>
      <td class="px-3 py-2 text-xs text-right font-mono font-bold ${c.total_score >= 50 ? 'text-green-700' : c.total_score >= 35 ? 'text-amber-700' : 'text-gray-500'}">${c.total_score}</td>
    </tr>
  `).join("");

  detailPanel.innerHTML = `
    <div class="mb-6">
      <div class="flex items-start justify-between mb-4">
        <div class="flex-1">
          <div class="flex items-center gap-3 mb-2">
            <h1 class="text-xl font-bold text-gray-900">${d.remitter || 'Unknown Remitter'}</h1>
            <span class="inline-flex items-center px-2.5 py-1 rounded-md text-[10px] font-bold ring-1 uppercase ${statusBadgeClass}">${d.status}</span>
          </div>
          <p class="text-xs text-gray-500 font-mono">${(d.eft_item || {}).description || ''}</p>
        </div>
        <div class="text-right ml-4 flex-shrink-0">
          <div class="text-2xl font-bold text-gray-900">AED ${d.amount ? d.amount.toLocaleString() : '-'}</div>
          <div class="text-xs text-gray-500">${d.transfer_date || ''}</div>
        </div>
      </div>

      <!-- Score breakdown -->
      <div class="bg-gradient-to-br from-slate-50 to-white border border-gray-200 rounded-lg p-4 mb-6 shadow-sm">
        <h3 class="text-xs font-bold text-gray-600 uppercase tracking-wider mb-3">Match Score Breakdown</h3>
        <div class="grid grid-cols-3 gap-4">
          <div class="text-center p-3 bg-white rounded-lg border border-gray-200 shadow-sm">
            <div class="text-2xl font-bold ${d.total_score >= 50 ? 'text-green-600' : d.total_score >= 35 ? 'text-amber-600' : 'text-gray-500'}">${d.total_score}</div>
            <div class="text-[10px] text-gray-500 uppercase font-bold mt-1">Total Score</div>
            <div class="text-[9px] text-gray-400">/ 100</div>
          </div>
          <div class="p-3 bg-white rounded-lg border border-gray-200 shadow-sm">
            <div class="text-[10px] text-gray-500 uppercase font-bold mb-2">Name Match (60%)</div>
            ${scoreBar(d.name_score, 100, 'bg-blue-500')}
          </div>
          <div class="p-3 bg-white rounded-lg border border-gray-200 shadow-sm">
            <div class="text-[10px] text-gray-500 uppercase font-bold mb-2">Amount Match (40%)</div>
            ${scoreBar(d.amount_score, 40, 'bg-emerald-500')}
          </div>
        </div>
      </div>

      ${card.customer_name ? `
        <!-- Matched card -->
        <div class="bg-gradient-to-br from-${d.status === 'matched' ? 'green' : 'amber'}-50 to-white border border-${d.status === 'matched' ? 'green' : 'amber'}-200 rounded-lg p-4 mb-6 shadow-sm">
          <h3 class="text-xs font-bold text-gray-600 uppercase tracking-wider mb-3">
            ${d.status === 'matched' ? '✓ Matched Customer Card' : '~ Best Candidate'}
          </h3>
          <div class="flex items-center gap-4">
            <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center text-white font-bold text-xl shadow-md flex-shrink-0">
              ${(card.customer_name || '?').charAt(0)}
            </div>
            <div class="flex-1">
              <div class="font-bold text-gray-900 text-base">${card.customer_name}</div>
              <div class="text-xs text-gray-500 mt-0.5">
                ${card.customer_id ? `ID: ${card.customer_id}` : ''}
                ${card.account_type ? ` · ${card.account_type}` : ''}
                ${card.currency ? ` · ${card.currency}` : ''}
              </div>
              ${card.credit_limit ? `<div class="text-xs text-gray-500">Credit Limit: ${card.currency || 'AED'} ${card.credit_limit.toLocaleString()}</div>` : ''}
            </div>
          </div>
        </div>
      ` : `
        <div class="bg-gray-50 border border-dashed border-gray-300 rounded-lg p-4 mb-6 text-center">
          <p class="text-sm text-gray-400 italic">No customer card matched this EFT payment</p>
        </div>
      `}

      <!-- All candidates -->
      ${(d.all_candidates || []).length > 0 ? `
        <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">All Candidates (Top 3)</h3>
        <div class="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden mb-6">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-3 py-2.5 text-left text-[10px] font-bold text-gray-600 uppercase">Customer</th>
                <th class="px-3 py-2.5 text-left text-[10px] font-bold text-gray-600 uppercase">ID</th>
                <th class="px-3 py-2.5 text-right text-[10px] font-bold text-gray-600 uppercase">Name</th>
                <th class="px-3 py-2.5 text-right text-[10px] font-bold text-gray-600 uppercase">Amount</th>
                <th class="px-3 py-2.5 text-right text-[10px] font-bold text-gray-600 uppercase">Total</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">${candidatesHtml}</tbody>
          </table>
        </div>
      ` : ''}

      <!-- Raw EFT description -->
      <div class="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Raw EFT Description</h3>
        <p class="text-xs text-gray-700 font-mono leading-relaxed break-all">${(d.eft_item || {}).description || '-'}</p>
      </div>
    </div>
  `;
}

function renderDhofarReconSummary(data) {
  const matched   = data.filter(d => d.status === 'matched');
  const partial   = data.filter(d => d.status === 'partial');
  const unmatched = data.filter(d => d.status === 'unmatched');
  const totalEft   = data.reduce((s, d) => s + (d.total_amount ?? d.amount ?? 0), 0);
  const matchedAmt = matched.reduce((s, d) => s + (d.amount || 0), 0);
  const partialAmt = partial.reduce((s, d) => s + (d.amount || 0), 0);

  // Inject summary into analytics bar area
  const bar = document.getElementById('analytics-bar');
  bar.classList.remove('hidden');
  bar.innerHTML = `
    <div class="flex items-center justify-between gap-6 flex-wrap">
      <div class="flex items-center gap-6">
        <div class="text-center">
          <div class="text-xl font-bold text-green-600">${matched.length}</div>
          <div class="text-[7.5px] text-gray-500 uppercase font-semibold mt-1">Matched</div>
        </div>
        <div class="text-center">
          <div class="text-xl font-bold text-amber-600">${partial.length}</div>
          <div class="text-[7.5px] text-gray-500 uppercase font-semibold mt-1">Partial</div>
        </div>
        <div class="text-center">
          <div class="text-xl font-bold text-gray-500">${unmatched.length}</div>
          <div class="text-[7.5px] text-gray-500 uppercase font-semibold mt-1">Unmatched</div>
        </div>
        <div class="h-10 w-px bg-gray-300"></div>
        <div class="text-center">
          <div class="text-xl font-bold text-indigo-600">${data.length > 0 ? Math.round(matched.length / data.length * 100) : 0}%</div>
          <div class="text-[7.5px] text-gray-500 uppercase font-semibold mt-1">Match Rate</div>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <div class="text-center px-3 py-2 bg-gradient-to-br from-green-500 to-green-600 rounded-lg shadow-sm min-w-[100px]">
          <div class="text-sm font-bold text-white">AED ${matchedAmt.toLocaleString()}</div>
          <div class="text-[8px] text-green-100 uppercase font-bold mt-0.5">Matched</div>
        </div>
        <div class="text-center px-3 py-2 bg-gradient-to-br from-amber-500 to-amber-600 rounded-lg shadow-sm min-w-[100px]">
          <div class="text-sm font-bold text-white">AED ${partialAmt.toLocaleString()}</div>
          <div class="text-[8px] text-amber-100 uppercase font-bold mt-0.5">Partial</div>
        </div>
        <div class="text-center px-3 py-2 bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg shadow-sm min-w-[100px]">
          <div class="text-sm font-bold text-white">AED ${totalEft.toLocaleString()}</div>
          <div class="text-[8px] text-blue-100 uppercase font-bold mt-0.5">Total EFT</div>
        </div>
        <button onclick="triggerDhofarRecon()" class="px-3 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold transition-all shadow-sm">
          ↻ Re-run
        </button>
      </div>
    </div>
  `;
}

window.triggerDhofarRecon = async () => {
  showToast('Running Dhofar reconciliation...', 'success');
  try {
    const res = await fetch('/api/dhofar/reconcile', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      const s = data.summary;
      showToast(`Done: ${s.bank_rows_matched} bank matched, ${s.invoices_cleared} invoices cleared`, 'success');
      renderDhofarReconciliation();
    } else {
      showToast('Reconciliation failed: ' + (data.detail || 'unknown error'), 'error');
    }
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
};

function filterDhofarRecon(term) {
  if (!window.dhofarReconData) return;
  const filtered = term
    ? window.dhofarReconData.filter(d => {
        const card = d.matched_card || d.best_candidate || {};
        return (
          (d.remitter || '').toLowerCase().includes(term) ||
          (card.customer_name || '').toLowerCase().includes(term) ||
          (card.customer_id || '').toLowerCase().includes(term) ||
          ((d.eft_item || {}).description || '').toLowerCase().includes(term)
        );
      })
    : window.dhofarReconData;
  renderDhofarReconList(filtered);
}
