document.addEventListener("DOMContentLoaded", () => {
    // State management
    let allProducts = [];
    let activeStoreFilter = "all";
    let showInStockOnly = false;
    let searchQuery = "";

    // DOM Elements
    const productsGrid = document.getElementById("products-grid");
    const loadingSpinner = document.getElementById("loading-spinner");
    const errorMessage = document.getElementById("error-message");
    const errorDetails = document.getElementById("error-details");
    const noProducts = document.getElementById("no-products");
    const searchInput = document.getElementById("search-input");
    const storeTabs = document.querySelectorAll(".tab-btn");
    const viewBtns = document.querySelectorAll(".view-btn");
    const instockToggle = document.getElementById("instock-only-toggle");
    const refreshBtn = document.getElementById("refresh-btn");
    const lastUpdatedSpan = document.getElementById("last-updated");

    // Stats Elements
    const statTotal = document.getElementById("stat-total");
    const statSales = document.getElementById("stat-sales");
    const statSoldout = document.getElementById("stat-soldout");

    // Helper: format price with commas
    function formatPrice(price) {
        try {
            if (price === 0 || !price) {
                return "가격 문의";
            }
            const numPrice = Number(price);
            if (isNaN(numPrice)) {
                return price + "원";
            }
            return numPrice.toLocaleString() + "원";
        } catch (e) {
            return "가격 문의";
        }
    }

    // Fetch products from products.json
    async function fetchProducts() {
        showLoading();
        try {
            console.log("Fetching products from products.json...");
            // Use cache-busting query to ensure fresh fetch of the json file
            const response = await fetch(`products.json?_=${Date.now()}`);
            if (!response.ok) {
                throw new Error(`데이터를 찾을 수 없습니다. (HTTP status: ${response.status})`);
            }
            const data = await response.json();
            if (data.success) {
                allProducts = data.products || [];
                console.log(`Successfully fetched ${allProducts.length} products.`);
                updateStats(allProducts);
                renderProducts();
                updateLastUpdated();
            } else {
                throw new Error("데이터 형식이 올바르지 않습니다.");
            }
        } catch (error) {
            console.error("fetchProducts error:", error);
            showError(error.stack || error.message || error);
        }
    }

    // Update stats panel
    function updateStats(products) {
        try {
            const total = products.length;
            let soldOutCount = 0;
            
            for (let i = 0; i < products.length; i++) {
                if (products[i] && products[i].soldOut) {
                    soldOutCount++;
                }
            }
            
            const inStockCount = total - soldOutCount;

            statTotal.textContent = total;
            statSales.textContent = inStockCount;
            statSoldout.textContent = soldOutCount;
        } catch (e) {
            console.error("Error updating stats:", e);
        }
    }

    // Render products into the grid
    function renderProducts() {
        try {
            productsGrid.innerHTML = "";
            
            const filteredProducts = allProducts.filter((product) => {
                if (!product) {
                    return false;
                }
                const storeName = product.store || "";
                const productName = product.name || "";
                const isSoldOut = !!product.soldOut;

                const matchesStore = (activeStoreFilter === "all" || storeName === activeStoreFilter);
                const matchesStock = (!showInStockOnly || !isSoldOut);
                const matchesSearch = productName.toLowerCase().includes(searchQuery.toLowerCase());
                
                return (matchesStore && matchesStock && matchesSearch);
            });

            if (filteredProducts.length === 0) {
                productsGrid.classList.add("hidden");
                noProducts.classList.remove("hidden");
                return;
            }

            noProducts.classList.add("hidden");
            productsGrid.classList.remove("hidden");

            filteredProducts.forEach((product, index) => {
                try {
                    const storeName = product.store || "알 수 없음";
                    const productName = product.name || "이름 없는 원두";
                    const productPrice = product.price || 0;
                    const productUrl = product.productUrl || "#";
                    const isSoldOut = !!product.soldOut;

                    const card = document.createElement("a");
                    card.href = productUrl;
                    card.target = "_blank";
                    card.className = `product-card ${isSoldOut ? "is-soldout" : ""}`;

                    let storeClass = "store-502";
                    if (storeName === "존스알커피") {
                        storeClass = "store-johns";
                    } else if (storeName === "딥다이브 로스터스") {
                        storeClass = "store-deepdive";
                    }

                    const imageUrl = product.imageUrl || `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect width="100" height="100" fill="%23ece0d1"/><text x="50" y="50" font-size="12" font-family="Noto Sans KR" font-weight="bold" fill="%237c5c43" dominant-baseline="middle" text-anchor="middle">No Image</text></svg>`;

                    let cardHTML = `
                        <div class="img-container">
                            <span class="store-badge ${storeClass}">${storeName}</span>
                            <img src="${imageUrl}" alt="${productName}" class="product-img" loading="lazy" onerror="this.src='https://placehold.co/300x300/f5eedc/4e3629?text=Coffee+Bean'">
                    `;

                    if (isSoldOut) {
                        cardHTML += `
                            <div class="soldout-overlay">
                                <span class="soldout-badge">품절</span>
                            </div>
                        `;
                    }

                    cardHTML += `
                        </div>
                        <div class="product-info">
                            <h3 class="product-name" title="${productName}">
                                <span class="store-text-label ${storeClass}">${storeName}</span>
                                <span class="name-text">${productName}</span>
                            </h3>
                            <div class="product-footer">
                                <div class="price-wrapper">
                                    <span class="price-label">판매 가격</span>
                                    <span class="price-value">${formatPrice(productPrice)}</span>
                                </div>
                                <span class="buy-link" title="상품 구매하러 가기">
                                    ➔
                                </span>
                            </div>
                        </div>
                    `;

                    card.innerHTML = cardHTML;
                    productsGrid.appendChild(card);
                } catch (cardError) {
                    console.error(`Error rendering card at index ${index}:`, cardError, product);
                }
            });

            hideLoading();
        } catch (renderError) {
            console.error("renderProducts error:", renderError);
            showError("화면 그리기 실패: " + renderError.stack || renderError.message);
        }
    }

    // Set view mode (grid, list, text)
    function setViewMode(viewMode) {
        try {
            productsGrid.classList.remove("view-list", "view-text");
            
            viewBtns.forEach((btn) => {
                if (btn && btn.getAttribute("data-view") === viewMode) {
                    btn.classList.add("active");
                } else if (btn) {
                    btn.classList.remove("active");
                }
            });

            if (viewMode === "list") {
                productsGrid.classList.add("view-list");
            } else if (viewMode === "text") {
                productsGrid.classList.add("view-text");
            }

            localStorage.setItem("coffee-view-mode", viewMode);
        } catch (e) {
            console.error("Error setting view mode:", e);
        }
    }

    // Update timestamp
    function updateLastUpdated() {
        try {
            const now = new Date();
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');
            lastUpdatedSpan.textContent = `동기화: 오늘 ${hours}:${minutes}:${seconds}`;
        } catch (e) {
            console.error("Error updating timestamp:", e);
        }
    }

    // UI State switch helpers
    function showLoading() {
        loadingSpinner.classList.remove("hidden");
        productsGrid.classList.add("hidden");
        errorMessage.classList.add("hidden");
        noProducts.classList.add("hidden");
    }

    function hideLoading() {
        loadingSpinner.classList.add("hidden");
    }

    function showError(details) {
        loadingSpinner.classList.add("hidden");
        productsGrid.classList.add("hidden");
        errorMessage.classList.remove("hidden");
        errorDetails.innerHTML = "<strong>상세 오류내용:</strong><br>" + details.replace(/\n/g, "<br>");
        lastUpdatedSpan.textContent = "업데이트 실패";
    }

    // Event Listeners
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            searchQuery = e.target.value.trim();
            renderProducts();
        });
    }

    storeTabs.forEach((tab) => {
        if (tab) {
            tab.addEventListener("click", () => {
                storeTabs.forEach((t) => {
                    if (t) {
                        t.classList.remove("active");
                    }
                });
                tab.classList.add("active");

                activeStoreFilter = tab.getAttribute("data-store");
                renderProducts();
            });
        }
    });

    viewBtns.forEach((btn) => {
        if (btn) {
            btn.addEventListener("click", () => {
                const view = btn.getAttribute("data-view");
                setViewMode(view);
            });
        }
    });

    if (instockToggle) {
        instockToggle.addEventListener("change", (e) => {
            showInStockOnly = e.target.checked;
            renderProducts();
        });
    }

    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            fetchProducts();
        });
    }

    // Initial View Mode Load
    const savedView = localStorage.getItem("coffee-view-mode") || "grid";
    setViewMode(savedView);

    // Initial load
    fetchProducts();
});
