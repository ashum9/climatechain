export class ClimateChainBadgeElement extends HTMLElement {
  static get observedAttributes() {
    return ["project-id", "case-title", "method", "census", "package-hash", "contract-address", "chain-id", "status"];
  }

  private root: ShadowRoot;

  constructor() {
    super();
    this.root = this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    this.render();
  }

  attributeChangedCallback() {
    this.render();
  }

  private render() {
    const projectId = this.getAttribute("project-id") || "TR-IZMIR-ORHANLI-2025";
    const caseTitle = this.getAttribute("case-title") || "İzmir / Orhanlı Fire";
    const method = this.getAttribute("method") || "Sentinel-2 L2A dNBR (35SMC)";
    const census = this.getAttribute("census") || "28 Acquisitions (June–July 2025)";
    const packageHash = this.getAttribute("package-hash") || "0x4030177336e456e398419c05a34f41d1d816246c79e186b8f11d9c130a479c44";
    const contractAddress = this.getAttribute("contract-address") || "0xb1ce2e8ceb392ad3bf0e011d05689058dfa9210f";
    const chainId = this.getAttribute("chain-id") || "11155111";
    const status = this.getAttribute("status") || "APPROVED";

    const shortHash = packageHash.length > 18 ? `${packageHash.slice(0, 10)}...${packageHash.slice(-6)}` : packageHash;
    const isApproved = status.toUpperCase() === "APPROVED";
    const accentColor = isApproved ? "#0D7680" : "#990F3D";
    const accentBg = isApproved ? "#EBF7F8" : "#FBF0F4";
    const accentBorder = isApproved ? "#99D8DC" : "#E8B4C4";

    this.root.innerHTML = `
      <style>
        :host {
          display: inline-block;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
          color: #33302E;
          font-size: 12px;
          user-select: none;
        }
        .badge-box {
          background: #FFFFFF;
          border: 1px solid #CCC0B3;
          border-top: 3px solid ${accentColor};
          padding: 12px 14px;
          display: inline-flex;
          flex-direction: column;
          gap: 6px;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
          max-width: 380px;
        }
        .header-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          border-bottom: 1px solid #E5D5C5;
          padding-bottom: 6px;
        }
        .title {
          font-family: "Source Serif 4", Georgia, serif;
          font-weight: 700;
          font-size: 13px;
          color: #33302E;
        }
        .status-pill {
          background: ${accentBg};
          color: ${accentColor};
          border: 1px solid ${accentBorder};
          padding: 2px 7px;
          font-size: 10px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .meta-grid {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 3px 12px;
          font-size: 11px;
        }
        .label {
          color: #766E65;
          font-weight: 500;
        }
        .val {
          color: #33302E;
          text-align: right;
          font-family: ui-monospace, Monaco, monospace;
        }
        .footer-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-top: 1px solid #E5D5C5;
          padding-top: 6px;
          font-size: 10px;
          color: #766E65;
        }
        .copy-btn {
          background: #FBF0E4;
          border: 1px solid #CCC0B3;
          color: #0F5499;
          padding: 2px 6px;
          cursor: pointer;
          font-family: ui-monospace, monospace;
          font-size: 10px;
        }
        .copy-btn:hover {
          background: #E5D5C5;
        }
        .etherscan-link {
          color: #0F5499;
          text-decoration: underline;
        }
        @media (forced-colors: active) {
          .badge-box {
            border: 1px solid CanvasText;
            background: Canvas;
            color: CanvasText;
          }
          .status-pill {
            border: 1px solid ButtonText;
            color: ButtonText;
          }
          .etherscan-link {
            color: LinkText;
          }
        }
      </style>
      <div class="badge-box">
        <div class="header-row">
          <span class="title">ClimateChain Verified Ledger</span>
          <span class="status-pill">${status}</span>
        </div>
        <div class="meta-grid">
          <span class="label">Investigation:</span>
          <span class="val">${projectId} (${caseTitle})</span>
          <span class="label">Method:</span>
          <span class="val">${method}</span>
          <span class="label">Census:</span>
          <span class="val" style="color: ${accentColor};">${census}</span>
          <span class="label">Ledger:</span>
          <span class="val">Sepolia (${chainId})</span>
        </div>
        <div class="footer-row">
          <button class="copy-btn" id="copy-btn" title="Click to copy full packageHash">${shortHash} 📋</button>
          <a class="etherscan-link" href="https://sepolia.etherscan.io/address/${contractAddress}" target="_blank">Etherscan ↗</a>
        </div>
      </div>
    `;

    const copyBtn = this.root.getElementById("copy-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(packageHash).then(() => {
          copyBtn.textContent = "Copied! ✓";
          setTimeout(() => {
            copyBtn.textContent = `${shortHash} 📋`;
          }, 1500);
        });
      });
    }
  }
}
