let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";

// Streaming state: the plan appears while it is being written.
let draftParts = [];
let draftTotal = 0;
let draftBuffer = "";
let finalBuffer = "";
let renderTimer = null;

const STAGE_MESSAGES = {
    supervisor: "Request checked. Searching flights, hotels and weather...",
    flight_agent: "Flights found.",
    hotel_agent: "Hotels found.",
    weather_agent: "Weather checked.",
    budget_agent: "Budget reviewed.",
    itinerary_agent: "Draft ready for your review.",
    human_approval: "Writing the final plan...",
    final_agent: "Final plan ready."
};

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

function setProgress(message) {
    const progress = document.getElementById("progressText");

    progress.textContent = message || "";
    progress.classList.toggle("hidden", !message);
}

function renderMarkdown(markdown) {
    const text = String(markdown || "");

    if (typeof marked === "undefined") {
        return null;
    }

    const html = marked.parse(text);
    return typeof DOMPurify !== "undefined" ? DOMPurify.sanitize(html) : html;
}

function paintResult(markdown) {
    const resultBox = document.getElementById("resultBox");
    const html = renderMarkdown(markdown);

    if (html !== null) {
        resultBox.innerHTML = html;
    } else {
        resultBox.innerText = markdown;
    }
}

// Re-rendering markdown on every token is wasteful, so paint at most every 120 ms.
function schedulePaint(getMarkdown) {
    if (renderTimer) {
        return;
    }

    renderTimer = setTimeout(() => {
        renderTimer = null;
        latestAnswerMarkdown = getMarkdown();
        paintResult(latestAnswerMarkdown);
    }, 120);
}

function draftFromParts() {
    const pieces = [];

    for (let i = 0; i < draftTotal; i++) {
        pieces.push(draftParts[i] || "*Writing the next days...*");
    }

    return pieces.join("\n\n");
}

function revealResultSection() {
    const resultSection = document.getElementById("resultSection");

    if (resultSection.classList.contains("hidden")) {
        resultSection.classList.remove("hidden");
        resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

function resetForNewRun(keepFlights) {
    draftParts = [];
    draftTotal = 0;
    draftBuffer = "";
    finalBuffer = "";
    latestAnswerMarkdown = "";

    if (renderTimer) {
        clearTimeout(renderTimer);
        renderTimer = null;
    }

    document.getElementById("resultBox").replaceChildren();
    document.getElementById("approvalPanel").classList.add("hidden");

    if (!keepFlights) {
        renderFlights([], "");
    }
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

// The final, authoritative render once the server says the run is finished.
function showResult(data) {
    if (renderTimer) {
        clearTimeout(renderTimer);
        renderTimer = null;
    }

    latestAnswerMarkdown = String(data.answer || "");
    paintResult(latestAnswerMarkdown);

    renderFlights(data.flight_options, data.flight_notice);
    showApproval(data.requires_approval, data.approval_request);

    document.getElementById("threadInfo").textContent = `Thread ID: ${data.thread_id}`;
    revealResultSection();
}

function handleEvent(event) {
    switch (event.type) {
        case "stage":
            setProgress(STAGE_MESSAGES[event.node] || "");
            break;

        case "flights":
            renderFlights(event.options, event.notice);
            revealResultSection();
            break;

        case "draft_part":
            draftTotal = event.total;
            draftParts[event.index] = event.text;
            revealResultSection();
            setProgress("Writing your itinerary...");
            schedulePaint(draftFromParts);
            break;

        case "draft_delta":
            draftBuffer += event.text;
            revealResultSection();
            setProgress("Writing your itinerary...");
            schedulePaint(() => draftBuffer);
            break;

        case "final_delta":
            finalBuffer += event.text;
            document.getElementById("approvalPanel").classList.add("hidden");
            setProgress("Writing the final plan...");
            schedulePaint(() => finalBuffer);
            break;

        case "done":
            currentThreadId = event.result.thread_id;
            localStorage.setItem("travel_thread_id", currentThreadId);
            showResult(event.result);
            break;

        case "error":
            throw new Error(event.error || "Something went wrong.");
    }
}

// Read a Server-Sent Events response and call handleEvent for each message.
async function streamRequest(url, body) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
    });

    if (!response.ok) {
        let message = "Something went wrong.";

        try {
            message = (await response.json()).error || message;
        } catch (ignored) {
            // keep the generic message
        }

        throw new Error(message);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { value, done } = await reader.read();

        if (done) {
            break;
        }

        buffer += decoder.decode(value, { stream: true });

        const messages = buffer.split("\n\n");
        buffer = messages.pop();

        for (const message of messages) {
            if (message.startsWith("data: ")) {
                handleEvent(JSON.parse(message.slice(6)));
            }
        }
    }
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
    resetForNewRun(false);
    setProgress("Checking your request...");

    try {
        await streamRequest("/api/travel/stream", {
            message: message,
            thread_id: currentThreadId
        });
    } catch (error) {
        showError(error.message);
    } finally {
        setProgress("");
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

    resetForNewRun(true);
    setProgress("Sending your decision...");

    try {
        await streamRequest("/api/travel/approve/stream", {
            thread_id: currentThreadId,
            approved: approved,
            feedback: feedback
        });
    } catch (error) {
        showError(error.message);
    } finally {
        setProgress("");
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
