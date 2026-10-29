let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";

function setPrompt(text) {
    document.getElementById("userInput").value = text;
}

function setLoading(isLoading) {
    const sendBtn = document.getElementById("sendBtn");
    const btnText = document.getElementById("btnText");
    const btnLoader = document.getElementById("btnLoader");

    sendBtn.disabled = isLoading;

    if (isLoading) {
        btnText.classList.add("hidden");
        btnLoader.classList.remove("hidden");
    } else {
        btnText.classList.remove("hidden");
        btnLoader.classList.add("hidden");
    }
}

function showError(message) {
    const errorBox = document.getElementById("errorBox");

    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
}

function hideError() {
    const errorBox = document.getElementById("errorBox");

    errorBox.classList.add("hidden");
    errorBox.textContent = "";
}

function renderMarkdown(markdown) {
    const text = String(markdown || "");

    if (typeof marked === "undefined") {
        return null;
    }

    const html = marked.parse(text);
    return typeof DOMPurify !== "undefined" ? DOMPurify.sanitize(html) : html;
}

function showApproval(requiresApproval, message) {
    const panel = document.getElementById("approvalPanel");

    panel.classList.toggle("hidden", !requiresApproval);

    if (requiresApproval) {
        document.getElementById("approvalText").textContent =
            message || "Please review the draft itinerary.";
        document.getElementById("feedbackInput").value = "";
    }
}

function renderFlights(options, notice) {
    const section = document.getElementById("flightSection");
    const rows = document.getElementById("flightRows");

    rows.replaceChildren();
    document.getElementById("flightNotice").textContent = notice || "";

    if (!options || options.length === 0) {
        section.classList.toggle("hidden", !notice);
        return;
    }

    options.forEach((flight) => {
        const row = document.createElement("tr");
        const cells = [
            flight.airline,
            flight.flight_number,
            `${flight.dep_iata} → ${flight.arr_iata}`,
            flight.date,
            flight.departs,
            flight.arrives
        ];

        cells.forEach((value) => {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.appendChild(cell);
        });

        rows.appendChild(row);
    });

    section.classList.remove("hidden");
}

function showResult(answer, threadId, requiresApproval = false, approvalMessage = "", flights = [], flightNotice = "") {
    latestAnswerMarkdown = String(answer || "");

    const resultSection = document.getElementById("resultSection");
    const resultBox = document.getElementById("resultBox");
    const threadInfo = document.getElementById("threadInfo");

    const html = renderMarkdown(latestAnswerMarkdown);

    if (html !== null) {
        resultBox.innerHTML = html;
    } else {
        resultBox.innerText = latestAnswerMarkdown;
    }

    renderFlights(flights, flightNotice);
    showApproval(requiresApproval, approvalMessage);

    threadInfo.textContent = `Thread ID: ${threadId}`;

    resultSection.classList.remove("hidden");

    resultSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

async function sendMessage() {
    hideError();

    const input = document.getElementById("userInput");
    const message = input.value.trim();

    if (!message) {
        showError("Please enter your travel request first.");
        return;
    }

    setLoading(true);

    try {
        const response = await fetch("/api/travel", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                thread_id: currentThreadId
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Something went wrong.");
        }

        currentThreadId = data.thread_id;
        localStorage.setItem("travel_thread_id", currentThreadId);

        showResult(
            data.answer,
            data.thread_id,
            data.requires_approval,
            data.approval_request,
            data.flight_options,
            data.flight_notice
        );

    } catch (error) {
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

async function submitApproval(approved) {
    hideError();

    const feedback = document.getElementById("feedbackInput").value.trim();

    if (!approved && !feedback) {
        showError("Please describe the changes you want before requesting a revision.");
        return;
    }

    const buttons = document.querySelectorAll("#approvalPanel button");
    buttons.forEach((button) => { button.disabled = true; });

    try {
        const response = await fetch("/api/travel/approve", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                thread_id: currentThreadId,
                approved: approved,
                feedback: feedback
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Something went wrong.");
        }

        showResult(
            data.answer,
            data.thread_id,
            data.requires_approval,
            data.approval_request,
            data.flight_options,
            data.flight_notice
        );

    } catch (error) {
        showError(error.message);
    } finally {
        buttons.forEach((button) => { button.disabled = false; });
    }
}

function copyResult() {
    const resultBox = document.getElementById("resultBox");
    const text = resultBox.innerText;

    if (!text) {
        return;
    }

    navigator.clipboard.writeText(text)
        .then(() => {
            const copyBtn = document.querySelector(".copy-btn");
            const oldText = copyBtn.textContent;

            copyBtn.textContent = "Copied!";

            setTimeout(() => {
                copyBtn.textContent = oldText;
            }, 1400);
        })
        .catch(() => {
            showError("Could not copy result.");
        });
}

function downloadPDF() {
    const pdfContent = document.getElementById("pdfContent");

    if (!latestAnswerMarkdown || !pdfContent) {
        showError("No travel plan available to download.");
        return;
    }

    const downloadBtn = document.querySelector(".download-btn");
    const oldText = downloadBtn.textContent;

    downloadBtn.textContent = "Preparing PDF...";
    downloadBtn.disabled = true;

    const options = {
        margin: 0.5,
        filename: "ai-travel-plan.pdf",
        image: {
            type: "jpeg",
            quality: 0.98
        },
        html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: "#ffffff"
        },
        jsPDF: {
            unit: "in",
            format: "a4",
            orientation: "portrait"
        },
        pagebreak: {
            mode: ["avoid-all", "css", "legacy"]
        }
    };

    html2pdf()
        .set(options)
        .from(pdfContent)
        .save()
        .then(() => {
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
        })
        .catch(() => {
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
            showError("Could not download PDF.");
        });
}

document.addEventListener("keydown", function(event) {
    if (event.ctrlKey && event.key === "Enter") {
        sendMessage();
    }
});