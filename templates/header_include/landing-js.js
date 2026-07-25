let currentGlobalBtcPrice = 64520.00;

// Store last known prices
const lastKnownPrices = {
    'BTCUSDT': null,
    'ETHUSDT': null,
    'TRXUSDT': null,
    'BNBUSDT': null,
    'USDCUSDT': null
};

// Map API symbols to HTML element IDs
const elementMapping = {
    'BTCUSDT': ['ticker-btc', 'table-btc'],
    'ETHUSDT': ['ticker-eth', 'table-eth'],
    'TRXUSDT': ['ticker-trx', 'table-trx'],
    'BNBUSDT': ['ticker-bnb', 'table-bnb'],
    'USDCUSDT': ['table-usdt']
};

// Update DOM elements with price data
function updateUIElement(symbol, price) {
    const formattedPrice = '$' + price.toLocaleString('en-US', {
        minimumFractionDigits: price < 1 ? 4 : 2,
        maximumFractionDigits: price < 1 ? 4 : 2
    });

    if (elementMapping[symbol]) {
        elementMapping[symbol].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.innerText = formattedPrice;
                el.style.color = ''; // بازگرداندن رنگ اصلی
            }
        });
    }
}

function switchTradingMode(mode) {
    const buyTab = document.getElementById('tab-buy');
    const sellTab = document.getElementById('tab-sell');
    const balanceLabel = document.getElementById('mock-balance-label');
    const walletDisplay = document.getElementById('mock-wallet-display');
    const amountDisplay = document.getElementById('mock-amount-display');
    const assetBadge = document.getElementById('mock-asset-badge');
    const percentBadge = document.getElementById('mock-percent-badge');
    const feeLabel = document.getElementById('mock-fee-label');
    const feeDisplay = document.getElementById('mock-fee-display');
    const actionBtn = document.getElementById('mock-action-btn');

    if (!buyTab || !sellTab) return;

    if (mode === 'buy') {
        buyTab.classList.add('bg-white', 'text-dark', 'shadow-sm');
        buyTab.classList.remove('text-muted');
        sellTab.classList.remove('bg-white', 'text-dark', 'shadow-sm');
        sellTab.classList.add('text-muted');

        if (balanceLabel) balanceLabel.innerText = "Asset to Allocate";
        if (walletDisplay) {
            walletDisplay.innerText = "Wallet: $12,450.00";
            walletDisplay.className = "text-primary fs-12";
        }
        if (amountDisplay) amountDisplay.innerText = "0.500000";
        if (assetBadge) assetBadge.innerText = "BTC";
        if (percentBadge) {
            percentBadge.className = "bg-primary text-white text-center rounded py-1 flex-grow-1 fs-10 fw-bold";
            percentBadge.style.borderRadius = "6px";
        }

        if (feeLabel) feeLabel.innerText = "Internal Flat Fee (0.05%)";
        if (feeDisplay) {
            const feeValue = (0.5 * currentGlobalBtcPrice * 0.0005);
            feeDisplay.innerText = "$" + feeValue.toFixed(2);
        }

        if (actionBtn) {
            actionBtn.innerText = "Execute Spot Buy";
            actionBtn.style.background = "#10b981";
            actionBtn.style.boxShadow = "0 4px 12px rgba(16,185,129,0.25)";
        }
    } else {
        sellTab.classList.add('bg-white', 'text-dark', 'shadow-sm');
        sellTab.classList.remove('text-muted');
        buyTab.classList.remove('bg-white', 'text-dark', 'shadow-sm');
        buyTab.classList.add('text-muted');

        if (balanceLabel) balanceLabel.innerText = "Asset to Liquidate";
        if (walletDisplay) {
            walletDisplay.innerText = "Available: 0.6450 BTC";
            walletDisplay.className = "text-danger fs-12";
        }
        if (amountDisplay) amountDisplay.innerText = "0.645000";
        if (assetBadge) assetBadge.innerText = "USDT";
        if (percentBadge) {
            percentBadge.className = "bg-danger text-white text-center rounded py-1 flex-grow-1 fs-10 fw-bold";
            percentBadge.style.borderRadius = "6px";
        }

        if (feeLabel) feeLabel.innerText = "Estimated Return (Net)";
        if (feeDisplay) {
            const netReturn = (0.6450 * currentGlobalBtcPrice) * 0.9995;
            feeDisplay.innerText = "$" + netReturn.toLocaleString('en-US', {maximumFractionDigits: 2});
        }

        if (actionBtn) {
            actionBtn.innerText = "Execute Spot Sell";
            actionBtn.style.background = "#ef4444";
            actionBtn.style.boxShadow = "0 4px 12px rgba(239,68,68,0.25)";
        }
    }
}

function setUIErrorState() {
    const tickers = ['table-btc', 'table-eth', 'table-trx', 'table-usdt', 'table-bnb',
        'ticker-btc', 'ticker-eth', 'ticker-trx', 'ticker-bnb'];

    tickers.forEach(id => {
        const el = document.getElementById(id);
        if (el && (el.innerText === "Loading..." || el.innerText === "")) {
            el.innerText = "--";
            el.style.color = "#9ca3af";
            el.setAttribute('title', "Real-time feed currently unavailable");
        }
    });
}

// Fetch prices from Binance with fallback support
async function fetchRibbonPrices() {
    const symbolsParam = encodeURIComponent('["BTCUSDT","ETHUSDT","TRXUSDT","BNBUSDT","USDCUSDT"]');
    const binanceUrl = `https://api.binance.com/api/v3/ticker/price?symbols=${symbolsParam}`;

    try {
        const response = await fetch(binanceUrl, {
            signal: AbortSignal.timeout(5000)
        });

        if (!response.ok) throw new Error("Binance API Blocked or Error");

        const data = await response.json();
        data.forEach(ticker => {
            const price = parseFloat(ticker.price);
            lastKnownPrices[ticker.symbol] = price;
            updateUIElement(ticker.symbol, price);

            if (ticker.symbol === 'BTCUSDT') {
                currentGlobalBtcPrice = price;
            }
        });
    } catch (error) {
        console.warn('Binance Direct Fetch Failed, trying fallback API...', error);

        // Try fallback API (CoinCap) if Binance is blocked
        try {
            const fallbackRes = await fetch('https://api.coincap.io/v2/assets?ids=bitcoin,ethereum,tron,binance-coin,tether');
            const fallbackData = await fallbackRes.json();

            const mapCoinCap = {
                'bitcoin': 'BTCUSDT',
                'ethereum': 'ETHUSDT',
                'tron': 'TRXUSDT',
                'binance-coin': 'BNBUSDT',
                'tether': 'USDCUSDT'
            };

            fallbackData.data.forEach(item => {
                const symbol = mapCoinCap[item.id];
                if (symbol) {
                    const price = parseFloat(item.priceUsd);
                    lastKnownPrices[symbol] = price;
                    updateUIElement(symbol, price);
                }
            });
        } catch (fallbackErr) {
            console.error('All APIs failed:', fallbackErr);
            setUIErrorState();
        }
    }
}

document.addEventListener('DOMContentLoaded', function () {
    fetchRibbonPrices();
    setInterval(fetchRibbonPrices, 4000);
});

document.addEventListener('DOMContentLoaded', function () {
    const lightbox = document.getElementById('workspaceLightbox');
    const lightboxImg = document.getElementById('lightboxTargetImg');
    const closeBtn = document.getElementById('closeLightboxBtn');

    if (!lightbox || !lightboxImg || !closeBtn) return;

    document.querySelectorAll('.viewport-body').forEach(wrapper => {
        wrapper.addEventListener('click', function () {
            const targetImg = this.querySelector('.workspace-img');
            if (targetImg) {
                lightboxImg.src = targetImg.src;
                lightboxImg.alt = targetImg.alt;
                lightbox.classList.add('active');
                document.body.style.overflow = 'hidden';
                closeBtn.focus(); // Move focus to close button for accessibility
            }
        });
    });

    const closeWorkspaceLightbox = () => {
        lightbox.classList.remove('active');
        document.body.style.overflow = '';
        setTimeout(() => {
            lightboxImg.src = '';
            lightboxImg.alt = '';
        }, 250);
    };

    closeBtn.addEventListener('click', closeWorkspaceLightbox);
    lightbox.addEventListener('click', function (e) {
        if (e.target === lightbox) {
            closeWorkspaceLightbox();
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && lightbox.classList.contains('active')) {
            closeWorkspaceLightbox();
        }
    });
});

document.addEventListener('DOMContentLoaded', () => {
    const wrapper = document.getElementById('backToTopWrapper');
    const progressPath = document.getElementById('progressPath');
    let animationFrameId = null;

    if (wrapper && progressPath) {
        // Calculate SVG circle circumference
        const pathLength = progressPath.getTotalLength();
        progressPath.style.strokeDasharray = `${pathLength} ${pathLength}`;
        progressPath.style.strokeDashoffset = pathLength;

        // Calculate scroll progress and update progress bar
        const updateScrollProgress = () => {
            const scrollTotal = document.documentElement.scrollHeight - window.innerHeight;
            const scrollCurrent = window.scrollY;

            // Show/hide button after 100px scroll
            if (scrollCurrent > 100) {
                wrapper.style.opacity = '1';
                wrapper.style.visibility = 'visible';
                wrapper.style.transform = 'translateY(0)';
            } else {
                wrapper.style.opacity = '0';
                wrapper.style.visibility = 'hidden';
                wrapper.style.transform = 'translateY(15px)';
            }

            // Calculate percentage and offset for SVG
            if (scrollTotal > 0) {
                const progress = pathLength - (scrollCurrent * pathLength / scrollTotal);
                progressPath.style.strokeDashoffset = Math.max(0, progress);
            }
        };

        // Run on scroll
        window.addEventListener('scroll', updateScrollProgress, {passive: true});
        updateScrollProgress(); // Initial run to check page position

        // Smooth scroll to top algorithm (Ease Out Cubic)
        const easeOutCubic = (t) => (--t) * t * t + 1;

        const smoothScrollToTop = (duration = 800) => {
            const startPosition = window.scrollY;
            let startTime = null;

            const animationStep = (currentTime) => {
                if (!startTime) startTime = currentTime;
                const timeElapsed = currentTime - startTime;
                const progress = Math.min(timeElapsed / duration, 1);

                const easeProgress = easeOutCubic(progress);
                window.scrollTo(0, startPosition * (1 - easeProgress));

                if (timeElapsed < duration) {
                    animationFrameId = requestAnimationFrame(animationStep);
                } else {
                    window.scrollTo(0, 0);
                    animationFrameId = null;
                    wrapper.focus(); // Return focus to button after scroll
                }
            };

            animationFrameId = requestAnimationFrame(animationStep);
        };

        // Button click handler
        wrapper.addEventListener('click', (e) => {
            e.preventDefault();
            if (animationFrameId) cancelAnimationFrame(animationFrameId);
            smoothScrollToTop(800);
        });

        // Keyboard support for accessibility
        wrapper.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (animationFrameId) cancelAnimationFrame(animationFrameId);
                smoothScrollToTop(800);
            }
        });

        // Cancel auto-scroll on manual user interaction
        const stopAutoScroll = () => {
            if (animationFrameId) {
                cancelAnimationFrame(animationFrameId);
                animationFrameId = null;
            }
        };

        window.addEventListener('wheel', stopAutoScroll, {passive: true});
        window.addEventListener('touchmove', stopAutoScroll, {passive: true});
    }
});

document.addEventListener("DOMContentLoaded", function () {
    const loaderOverlay = document.getElementById("pageLoader");
    const loaderPercent = document.getElementById("loaderPercent");
    const loaderCircle = document.getElementById("loaderCircle");
    const loaderCard = document.getElementById("loaderCard");

    const radius = loaderCircle.r.baseVal.value;
    const circumference = 2 * Math.PI * radius;

    loaderCircle.style.strokeDasharray = `${circumference} ${circumference}`;
    loaderCircle.style.strokeDashoffset = circumference;

    const maxBlurPx = 12;
    const MIN_DISPLAY_TIME = 800; // Minimum loader display time in milliseconds (0.8 seconds)
    const startTime = Date.now();

    function updateLoaderUI(percent) {
        const currentProgress = Math.min(Math.max(percent, 0), 100);

        loaderPercent.textContent = `${Math.round(currentProgress)}%`;

        const offset = circumference - (currentProgress / 100) * circumference;
        loaderCircle.style.strokeDashoffset = offset;

        const blurAmount = maxBlurPx * (1 - (currentProgress / 100));
        loaderOverlay.style.backdropFilter = `blur(${blurAmount}px)`;
        loaderOverlay.style.webkitBackdropFilter = `blur(${blurAmount}px)`;

        if (currentProgress >= 100) {
            loaderCard.classList.add("finish-pop");
            setTimeout(() => {
                loaderOverlay.classList.add("fade-out");
                // Remove from DOM after fade out for better performance
                setTimeout(() => {
                    loaderOverlay.style.display = 'none';
                }, 600);
            }, 350);
        }
    }

    let progress = 0;
    const loaderInterval = setInterval(() => {
        if (progress < 90) {
            progress += Math.floor(Math.random() * 8) + 3;
            updateLoaderUI(progress);
        }
    }, 40);

    // When page is fully loaded
    window.addEventListener("load", function () {
        clearInterval(loaderInterval);

        const elapsedTime = Date.now() - startTime;
        const remainingTime = Math.max(0, MIN_DISPLAY_TIME - elapsedTime);

        // If loaded very quickly, delay slightly to 100% so animation completes
        setTimeout(() => {
            updateLoaderUI(100);
        }, remainingTime);
    });
});