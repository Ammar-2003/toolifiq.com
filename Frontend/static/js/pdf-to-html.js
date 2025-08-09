document.addEventListener('DOMContentLoaded', function() {
    // Configuration
    const BACKEND_URL = 'http://127.0.0.1:8000'; // Match your Django server
    const API_ENDPOINT = `${BACKEND_URL}/api/pdf-to-html/`;
    const STATUS_ENDPOINT = `${BACKEND_URL}/api/conversion-status/`;

    // DOM Elements
    const fileInput = document.getElementById('pdf-file');
    const convertBtn = document.getElementById('convert-btn');
    const conversionTypeSelect = document.getElementById('conversion-type');
    const filePreview = document.getElementById('file-preview');
    const conversionStatus = document.getElementById('conversion-status');
    const downloadLinkContainer = document.getElementById('download-link-container');
    
    // State
    let currentTaskId = null;
    let pollInterval = null;

    // Utility Functions
    const getCookie = (name) => {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [cookieName, cookieValue] = cookie.trim().split('=');
            if (cookieName === name) return decodeURIComponent(cookieValue);
        }
        return null;
    };

    const showStatus = (type, message) => {
        const statusTypes = {
            info: { bg: 'bg-blue-100', border: 'border-blue-500', text: 'text-blue-700', icon: 'fa-info-circle' },
            success: { bg: 'bg-green-100', border: 'border-green-500', text: 'text-green-700', icon: 'fa-check-circle' },
            error: { bg: 'bg-red-100', border: 'border-red-500', text: 'text-red-700', icon: 'fa-exclamation-circle' },
            loading: { bg: 'bg-blue-100', border: 'border-blue-500', text: 'text-blue-700', icon: 'fa-spinner fa-spin' }
        };
        
        const status = statusTypes[type] || statusTypes.info;
        conversionStatus.innerHTML = `
            <div class="${status.bg} border-l-4 ${status.border} ${status.text} p-4 mb-4">
                <p><i class="fas ${status.icon} mr-2"></i> ${message}</p>
            </div>
        `;
    };

    const handleFilePreview = (file) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            filePreview.innerHTML = `
                <div class="mb-4">
                    <embed src="${e.target.result}#toolbar=0&navpanes=0&scrollbar=0" type="application/pdf" width="100%" height="300px">
                </div>
                <div class="bg-white p-3 rounded-md shadow-sm">
                    <p class="text-sm font-medium text-gray-700">
                        <i class="fas fa-file-pdf mr-2"></i> ${file.name}
                    </p>
                    <p class="text-xs text-gray-500 mt-1">
                        <i class="fas fa-info-circle mr-2"></i> ${(file.size/1024).toFixed(2)} KB
                    </p>
                </div>
            `;
        };
        reader.readAsDataURL(file);
    };

    const validateFile = (file) => {
        const validTypes = ['application/pdf'];
        const validExtensions = /\.pdf$/i;
        
        if (!validTypes.includes(file.type) && !validExtensions.test(file.name)) {
            showStatus('error', 'Only PDF files are allowed');
            fileInput.value = '';
            return false;
        }
        
        if (file.size > 20 * 1024 * 1024) { // 20MB limit
            showStatus('error', 'File size too large (max 20MB)');
            fileInput.value = '';
            return false;
        }
        
        return true;
    };

    const pollConversionStatus = async (taskId) => {
        try {
            const response = await fetch(`${STATUS_ENDPOINT}${taskId}/`);
            if (!response.ok) {
                throw new Error('Failed to check conversion status');
            }
            
            const data = await response.json();
            
            if (data.status === 'COMPLETED') {
                clearInterval(pollInterval);
                showStatus('success', 'Conversion completed!');
                showDownloadButton(data);
            } else if (data.status === 'FAILED') {
                clearInterval(pollInterval);
                showStatus('error', `Conversion failed: ${data.error || 'Unknown error'}`);
                resetConvertButton();
            }
            // If still processing, do nothing - we'll check again
        } catch (error) {
            console.error('Error polling status:', error);
            clearInterval(pollInterval);
            showStatus('error', 'Failed to check conversion status');
            resetConvertButton();
        }
    };

    const showDownloadButton = (taskData) => {
        downloadLinkContainer.innerHTML = `
            <button id="download-btn" class="custom-download-btn">
                <i class="fas fa-download"></i>
                <span>Download HTML</span>
            </button>
        `;
        
        document.getElementById('download-btn').addEventListener('click', () => {
            handleDownload(taskData);
        });
        
        resetConvertButton();
    };

    const handleDownload = async (taskData) => {
        try {
            showStatus('loading', 'Preparing download...');
            
            if (!taskData.download_url) {
                throw new Error('No download URL available');
            }

            const response = await fetch(taskData.download_url);
            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}`);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            
            // Extract filename from URL or use default
            const filename = taskData.download_url.split('/').pop() || 'converted.html';
            a.download = filename;
            
            document.body.appendChild(a);
            a.click();
            
            setTimeout(() => {
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            }, 100);

            showStatus('success', 'Download started!');
        } catch (error) {
            console.error('Download failed:', error);
            showStatus('error', `Download failed: ${error.message}`);
        }
    };

    const resetConvertButton = () => {
        convertBtn.disabled = false;
        convertBtn.innerHTML = '<i class="fas fa-exchange-alt mr-2"></i> Convert to HTML';
    };

    const startConversionPolling = (taskId) => {
        // Clear any existing polling
        if (pollInterval) {
            clearInterval(pollInterval);
        }
        
        // Start new polling every 2 seconds
        pollInterval = setInterval(() => pollConversionStatus(taskId), 2000);
    };

    // Event Listeners
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            if (validateFile(file)) {
                showStatus('info', 'File ready for conversion');
                handleFilePreview(file);
                currentTaskId = null;
                
                // Clear any existing download button
                downloadLinkContainer.innerHTML = '';
            }
        }
    });

    convertBtn.addEventListener('click', async () => {
        if (!fileInput.files.length) {
            showStatus('error', 'Please select a file first');
            return;
        }

        // Get conversion type
        const conversionType = conversionTypeSelect.value || 'formatted';

        convertBtn.disabled = true;
        convertBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Converting...';
        showStatus('loading', 'Starting conversion...');
        downloadLinkContainer.innerHTML = '';

        try {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('conversion_type', conversionType);

            const response = await fetch(API_ENDPOINT, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.error || 'Conversion failed to start');
            }

            const data = await response.json();
            currentTaskId = data.task_id;
            
            showStatus('loading', 'Conversion in progress...');
            startConversionPolling(currentTaskId);

        } catch (error) {
            console.error('Conversion error:', error);
            showStatus('error', error.message);
            resetConvertButton();
        }
    });
});