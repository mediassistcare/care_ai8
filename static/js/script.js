// Global utility functions
function showLoading() {
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = 'flex';
    }
}

function hideLoading() {
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = 'none';
    }
}

// Form validation utilities
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function validateNumericInput(input, min, max) {
    const value = parseFloat(input.value);
    if (isNaN(value) || value < min || value > max) {
        input.classList.add('error');
        return false;
    }
    input.classList.remove('error');
    return true;
}

// Progress bar functionality
function updateProgressBar() {
    const currentStep = getCurrentStep();
    const progressSteps = document.querySelectorAll('.progress-step');
    
    progressSteps.forEach((step, index) => {
        step.classList.remove('active', 'completed');
        if (index < currentStep - 1) {
            step.classList.add('completed');
        } else if (index === currentStep - 1) {
            step.classList.add('active');
        }
    });
}

function getCurrentStep() {
    const path = window.location.pathname;
    if (path.includes('step1') || path === '/') return 1;
    if (path.includes('step2')) return 2;
    if (path.includes('step3')) return 3;
    if (path.includes('step4')) return 4;
    if (path.includes('step5')) return 5;
    if (path.includes('step6')) return 6;
    return 1;
}

// BMI Calculator
function calculateBMI(height, weight, heightUnit = 'cm', weightUnit = 'kg') {
    try {
        const heightVal = parseFloat(height);
        const weightVal = parseFloat(weight);
        
        if (!heightVal || !weightVal || heightVal <= 0 || weightVal <= 0) {
            return null;
        }
        
        // Convert to metric if needed
        let heightM = heightUnit === 'inches' ? heightVal * 0.0254 : heightVal / 100;
        let weightKg = weightUnit === 'lbs' ? weightVal * 0.453592 : weightVal;
        
        // Calculate BMI
        const bmi = weightKg / (heightM * heightM);
        return Math.round(bmi * 10) / 10; // Round to 1 decimal place
    } catch (error) {
        console.error('BMI calculation error:', error);
        return null;
    }
}

function getBMICategory(bmi) {
    if (!bmi || bmi <= 0) return '';
    if (bmi < 18.5) return '(Underweight)';
    if (bmi < 25) return '(Normal)';
    if (bmi < 30) return '(Overweight)';
    return '(Obese)';
}

// Form submission handlers
function handleFormSubmission(form, endpoint, successRedirect) {
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Validate form before submission
        if (!validateForm(form)) {
            return;
        }
        
        showLoading();
        
        const formData = new FormData(form);
        
        fetch(endpoint, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            hideLoading();
            if (data.success) {
                window.location.href = successRedirect;
            } else {
                showError(data.message || 'An error occurred while saving data.');
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Form submission error:', error);
            showError('Network error. Please check your connection and try again.');
        });
    });
}

function handleJSONSubmission(form, endpoint, successRedirect) {
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        showLoading();
        
        const formData = new FormData(form);
        const data = {};
        
        for (let [key, value] of formData.entries()) {
            data[key] = value;
        }
        
        fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(responseData => {
            hideLoading();
            if (responseData.success) {
                window.location.href = successRedirect;
            } else {
                showError(responseData.message || 'An error occurred while saving data.');
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Form submission error:', error);
            showError('Network error. Please check your connection and try again.');
        });
    });
}

// Form validation
function validateForm(form) {
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.classList.add('error');
            isValid = false;
        } else {
            field.classList.remove('error');
        }
        
        // Special validation for numeric fields
        if (field.type === 'number') {
            const min = parseFloat(field.getAttribute('min')) || 0;
            const max = parseFloat(field.getAttribute('max')) || Infinity;
            const value = parseFloat(field.value);
            
            if (isNaN(value) || value < min || value > max) {
                field.classList.add('error');
                isValid = false;
            }
        }
    });
    
    if (!isValid) {
        showError('Please fill in all required fields correctly.');
    }
    
    return isValid;
}

// Error handling
function showError(message) {
    // Create or update error message
    let errorDiv = document.querySelector('.error-message');
    if (!errorDiv) {
        errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.style.cssText = `
            background: #f8d7da;
            color: #721c24;
            padding: 12px 20px;
            border: 1px solid #f5c6cb;
            border-radius: 8px;
            margin: 20px 0;
            text-align: center;
            font-weight: 500;
        `;
        
        // Insert at the top of the main content
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.insertBefore(errorDiv, mainContent.firstChild);
        }
    }
    
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }
    }, 5000);
    
    // Scroll to error message
    errorDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// Tooltips functionality
function addTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    
    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', function(e) {
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.textContent = this.getAttribute('data-tooltip');
            
            document.body.appendChild(tooltip);
            
            const rect = this.getBoundingClientRect();
            tooltip.style.cssText = `
                position: absolute;
                top: ${rect.top - tooltip.offsetHeight - 5}px;
                left: ${rect.left + rect.width / 2 - tooltip.offsetWidth / 2}px;
                background: #333;
                color: white;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 14px;
                z-index: 10000;
                pointer-events: none;
                white-space: nowrap;
            `;
            
            this._tooltip = tooltip;
        });
        
        element.addEventListener('mouseleave', function() {
            if (this._tooltip) {
                this._tooltip.remove();
                this._tooltip = null;
            }
        });
    });
}

// Accessibility improvements
function addAccessibilityFeatures() {
    // Add keyboard navigation
    document.addEventListener('keydown', function(e) {
        // Enter key to submit forms
        if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA') {
            const form = e.target.closest('form');
            if (form) {
                const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                if (submitBtn && !submitBtn.disabled) {
                    e.preventDefault();
                    submitBtn.click();
                }
            }
        }
        
        // Escape key to close overlays
        if (e.key === 'Escape') {
            hideLoading();
            // Close any open tooltips
            document.querySelectorAll('.tooltip').forEach(tooltip => tooltip.remove());
        }
    });
    
    // Add focus indicators
    document.addEventListener('focusin', function(e) {
        if (e.target.matches('input, select, textarea, button')) {
            e.target.style.outline = '2px solid #3498db';
            e.target.style.outlineOffset = '2px';
        }
    });
    
    document.addEventListener('focusout', function(e) {
        if (e.target.matches('input, select, textarea, button')) {
            e.target.style.outline = '';
            e.target.style.outlineOffset = '';
        }
    });
}

// Auto-save functionality (for better UX)
function setupAutoSave() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        if (form.id) {
            const inputs = form.querySelectorAll('input, select, textarea');
            
            inputs.forEach(input => {
                input.addEventListener('input', debounce(() => {
                    saveFormData(form);
                }, 1000));
            });
            
            // Load saved data on page load
            loadFormData(form);
        }
    });
}

function saveFormData(form) {
    try {
        const formData = new FormData(form);
        const data = {};
        
        for (let [key, value] of formData.entries()) {
            if (key !== 'csrf_token') { // Don't save CSRF tokens
                data[key] = value;
            }
        }
        
        sessionStorage.setItem(`form_${form.id}`, JSON.stringify(data));
    } catch (error) {
        console.error('Error saving form data:', error);
    }
}

function loadFormData(form) {
    try {
        const savedData = sessionStorage.getItem(`form_${form.id}`);
        if (savedData) {
            const data = JSON.parse(savedData);
            Object.keys(data).forEach(key => {
                const input = form.querySelector(`[name="${key}"]`);
                if (input && input.type !== 'hidden') {
                    input.value = data[key];
                    
                    // Trigger change event for any listeners
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                }
            });
        }
    } catch (error) {
        console.error('Error loading form data:', error);
    }
}

function clearFormData(formId) {
    try {
        sessionStorage.removeItem(`form_${formId}`);
    } catch (error) {
        console.error('Error clearing form data:', error);
    }
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Network status handling
function setupNetworkHandling() {
    window.addEventListener('online', function() {
        console.log('Connection restored');
        hideError();
    });

    window.addEventListener('offline', function() {
        console.log('Connection lost');
        hideLoading();
        showError('Internet connection lost. Please check your connection and try again.');
    });
}

function hideError() {
    const errorDiv = document.querySelector('.error-message');
    if (errorDiv) {
        errorDiv.style.display = 'none';
    }
}

// Initialize everything when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Progress bar is now handled server-side in base.html template
    // updateProgressBar(); // Commented out to avoid conflicts
    
    // Add accessibility features
    addAccessibilityFeatures();
    
    // Add tooltips
    addTooltips();
    
    // Setup auto-save
    setupAutoSave();
    
    // Setup network handling
    setupNetworkHandling();
    
    // Auto-focus first input
    const firstInput = document.querySelector('input:not([type="hidden"]), textarea, select');
    if (firstInput) {
        firstInput.focus();
    }
    
    // Add real-time validation to numeric inputs
    const numericInputs = document.querySelectorAll('input[type="number"]');
    numericInputs.forEach(input => {
        input.addEventListener('blur', function() {
            const min = parseFloat(this.getAttribute('min')) || 0;
            const max = parseFloat(this.getAttribute('max')) || Infinity;
            validateNumericInput(this, min, max);
        });
        
        input.addEventListener('input', function() {
            this.classList.remove('error');
        });
    });
    
    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
});

// Enhanced error handling
window.addEventListener('error', function(e) {
    console.error('JavaScript error:', e);
    hideLoading();
});

window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e);
    hideLoading();
});

// Export functions for use in other scripts
if (typeof window !== 'undefined') {
    window.CareApp = {
        showLoading,
        hideLoading,
        calculateBMI,
        getBMICategory,
        validateForm,
        showError,
        hideError,
        handleFormSubmission,
        handleJSONSubmission,
        updateProgressBar
    };
}

// AI Insights functionality for medical report uploads
function setupMedicalReportUpload() {
    // Lab report upload handler
    const labReportFile = document.getElementById('lab_report_file');
    if (labReportFile) {
        labReportFile.addEventListener('change', function(e) {
            if (e.target.files.length > 0) {
                generateAIInsights('lab', e.target.files[0]);
            }
        });
    }

    // Medical image upload handler
    const medicalImageFile = document.getElementById('medical_image_file');
    if (medicalImageFile) {
        medicalImageFile.addEventListener('change', function(e) {
            if (e.target.files.length > 0) {
                generateAIInsights('image', e.target.files[0]);
            }
        });
    }

    // Pathology report upload handler
    const pathologyReportFile = document.getElementById('pathology_report_file');
    if (pathologyReportFile) {
        pathologyReportFile.addEventListener('change', function(e) {
            if (e.target.files.length > 0) {
                generateAIInsights('pathology', e.target.files[0]);
            }
        });
    }

    // Signaling report upload handler
    const signalingReportFile = document.getElementById('signaling_report_file');
    if (signalingReportFile) {
        signalingReportFile.addEventListener('change', function(e) {
            if (e.target.files.length > 0) {
                generateAIInsights('signaling', e.target.files[0]);
            }
        });
    }
}

// Generate AI insights for uploaded medical reports
async function generateAIInsights(reportType, file) {
    console.log(`Generating AI insights for ${reportType}: ${file.name}`);
    
    const container = document.getElementById(`${reportType}_insights_container`);
    const loader = document.getElementById(`${reportType}_insights_loader`);
    const content = document.getElementById(`${reportType}_insights_content`);
    const hiddenInput = document.getElementById(`${reportType}_ai_insights`);
    
    if (!container || !loader || !content) {
        console.error(`AI insights elements not found for ${reportType}`);
        return;
    }

    // Show the container and loader
    container.style.display = 'block';
    loader.style.display = 'block';
    content.innerHTML = '';

    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('report_type', reportType);

        const response = await fetch('/analyze_medical_report', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        
        // Hide loader
        loader.style.display = 'none';

        if (result.success) {
            // Display AI insights
            content.innerHTML = formatAIInsights(result.insights);
            
            // Store insights in hidden input for form submission
            if (hiddenInput) {
                hiddenInput.value = JSON.stringify(result.insights);
            }
            
            console.log(`AI insights generated successfully for ${reportType}`);
        } else {
            console.error(`Failed to analyze ${reportType}:`, result.error);
            content.innerHTML = `<div style="color: #e74c3c; padding: 10px;">
                <i class="fas fa-exclamation-triangle"></i> 
                ${result.error || 'Failed to analyze the report. Please try again.'}
            </div>`;
        }
    } catch (error) {
        console.error(`Error generating AI insights for ${reportType}:`, error);
        loader.style.display = 'none';
        content.innerHTML = `<div style="color: #e74c3c; padding: 10px;">
            <i class="fas fa-exclamation-triangle"></i> 
            Error analyzing report: ${error.message}
        </div>`;
    }
}

// Format AI insights for display
function formatAIInsights(insights) {
    if (!insights) return '<p>No insights available.</p>';
    
    let html = '';
    
    if (insights.summary) {
        html += `<div style="margin-bottom: 15px;">
            <h6 style="color: #2c3e50; margin-bottom: 8px;"><i class="fas fa-clipboard-list"></i> Summary</h6>
            <p style="margin-bottom: 0;">${insights.summary}</p>
        </div>`;
    }
    
    if (insights.key_findings && insights.key_findings.length > 0) {
        html += `<div style="margin-bottom: 15px;">
            <h6 style="color: #2c3e50; margin-bottom: 8px;"><i class="fas fa-search"></i> Key Findings</h6>
            <ul style="margin-bottom: 0; padding-left: 20px;">`;
        
        insights.key_findings.forEach(finding => {
            html += `<li style="margin-bottom: 5px;">${finding}</li>`;
        });
        
        html += `</ul></div>`;
    }
    
    if (insights.recommendations && insights.recommendations.length > 0) {
        html += `<div style="margin-bottom: 15px;">
            <h6 style="color: #2c3e50; margin-bottom: 8px;"><i class="fas fa-lightbulb"></i> Recommendations</h6>
            <ul style="margin-bottom: 0; padding-left: 20px;">`;
        
        insights.recommendations.forEach(recommendation => {
            html += `<li style="margin-bottom: 5px;">${recommendation}</li>`;
        });
        
        html += `</ul></div>`;
    }
    
    if (insights.abnormal_values && insights.abnormal_values.length > 0) {
        html += `<div style="margin-bottom: 15px;">
            <h6 style="color: #e74c3c; margin-bottom: 8px;"><i class="fas fa-exclamation-triangle"></i> Abnormal Values</h6>
            <ul style="margin-bottom: 0; padding-left: 20px;">`;
        
        insights.abnormal_values.forEach(value => {
            html += `<li style="margin-bottom: 5px; color: #e74c3c;">${value}</li>`;
        });
        
        html += `</ul></div>`;
    }
    
    if (insights.follow_up) {
        html += `<div style="margin-bottom: 0;">
            <h6 style="color: #2c3e50; margin-bottom: 8px;"><i class="fas fa-calendar-check"></i> Follow-up</h6>
            <p style="margin-bottom: 0;">${insights.follow_up}</p>
        </div>`;
    }
    
    return html || '<p>Analysis completed. No specific insights to display.</p>';
}

// Initialize medical report upload functionality when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    setupMedicalReportUpload();
});