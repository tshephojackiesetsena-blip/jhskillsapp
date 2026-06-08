// ===============================
// CRM APP JAVASCRIPT
// ===============================

// Runs when page loads
document.addEventListener("DOMContentLoaded", function () {
    console.log("CRM system loaded");

    initializeTheme();
    showWelcomeMessage();
    setupFormValidation();
    showAnnouncement();
});


// ===============================
// WELCOME MESSAGE (Dashboard)
// ===============================
function showWelcomeMessage() {
    const welcomeBox = document.getElementById("welcome-message");

    if (welcomeBox) {
        const userName = "User"; // later replace with real user
        welcomeBox.innerText = "Welcome back, " + userName + " 👋";
    }
}


// ===============================
// FORM VALIDATION
// ===============================
function setupFormValidation() {

    // LOGIN FORM
    const loginForm = document.getElementById("loginForm");

    if (loginForm) {
        loginForm.addEventListener("submit", function (e) {

            let email = document.getElementById("email").value.trim();
            let password = document.getElementById("password").value.trim();

            if (email === "") {
                alert("Please enter your email");
                e.preventDefault();
                return;
            }

            if (password === "") {
                alert("Please enter your password");
                e.preventDefault();
                return;
            }
        });
    }

    // REGISTER FORM
    const registerForm = document.getElementById("registerForm");

    if (registerForm) {
        registerForm.addEventListener("submit", function (e) {

            let name = document.getElementById("name").value.trim();
            let email = document.getElementById("email").value.trim();
            let phone = document.getElementById("phone").value.trim();
            let role = document.getElementById("role").value;
            let password = document.getElementById("password").value;
            let confirmPassword = document.getElementById("confirm_password").value;

            if (name === "") {
                alert("Enter full name");
                e.preventDefault();
                return;
            }

            if (email === "") {
                alert("Enter email");
                e.preventDefault();
                return;
            }

            if (phone === "") {
                alert("Enter phone number");
                e.preventDefault();
                return;
            }

            if (role === "") {
                alert("Select a role");
                e.preventDefault();
                return;
            }

            if (password === "") {
                alert("Enter password");
                e.preventDefault();
                return;
            }

            if (password !== confirmPassword) {
                alert("Passwords do not match");
                e.preventDefault();
                return;
            }
        });
    }
}


// ===============================
// SIDEBAR TOGGLE (Mobile Feel)
// ===============================
function toggleSidebar() {
    const sidebar = document.querySelector(".sidebar");

    if (sidebar) {
        sidebar.classList.toggle("active");
    }
}


// ===============================
// ANNOUNCEMENT SYSTEM 🔥
// ===============================
function showAnnouncement() {
    const announcementBox = document.getElementById("announcement");

    if (announcementBox) {
        announcementBox.innerText = "📢 New learners have been added to the system!";
    }
}


// ===============================
// SIMPLE BUTTON CLICK FEEDBACK
// ===============================
function showMessage(message) {
    alert(message);
}


// ===============================
// THEME TOGGLE
// ===============================
function initializeTheme() {
    const savedTheme = localStorage.getItem("jh_theme") || "light";
    applyTheme(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.body.getAttribute("data-theme") || "light";
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    localStorage.setItem("jh_theme", nextTheme);
}

function applyTheme(theme) {
    document.body.setAttribute("data-theme", theme);
    updateThemeButtons(theme);
}

function updateThemeButtons(theme) {
    document.querySelectorAll(".theme-toggle-btn").forEach((button) => {
        button.innerText = theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode";
    });
}
