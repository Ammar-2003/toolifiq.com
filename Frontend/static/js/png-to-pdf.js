document.addEventListener('DOMContentLoaded', function() {
    const BACKEND_URL = 'http://127.0.0.1:8000';
    const API_ENDPOINT = `${BACKEND_URL}/api/png-to-pdf/`;
    const CONVERSION_TIMEOUT = 60000;

    // DOM Elements
    const fileInput = document.getElementById('png-file');
    const convertBtn = document.getElementById('convert-btn');
    const filePreview = document.getElementById('file-preview');
    const conversionStatus = document.getElementById('conversion-status');
    const downloadLinkContainer = document.getElementById('download-link-container');
    const fileListContainer = document.getElementById('file-list-container');
    
    // State
    let currentConversion = null;
    let abortController = null;
    let selectedFiles = [];

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

    const renderFilePreviews = (files) => {
        if (files.length === 0) {
            filePreview.innerHTML = '<div class="text-gray-500 p-4 text-center">No files selected</div>';
            fileListContainer.innerHTML = '';
            return;
        }

        // Show first file as main preview
        const mainFile = files[0];
        const reader = new FileReader();
        reader.onload = (e) => {
            filePreview.innerHTML = `
                <div class="image-preview-container h-64 flex items-center justify-center">
                    <img src="${e.target.result}" 
                         alt="Preview" 
                         class="max-h-full max-w-full object-contain">
                </div>
                <div class="bg-white p-3 rounded-md shadow-sm mt-2">
                    <p class="text-sm font-medium text-gray-700">
                        <i class="fas fa-image mr-2"></i> ${mainFile.name}
                    </p>
                    <p class="text-xs text-gray-500 mt-1">
                        ${(mainFile.size/1024).toFixed(2)} KB
                    </p>
                </div>
            `;
        };
        reader.readAsDataURL(mainFile);

        // Show all files in a list
        fileListContainer.innerHTML = `
            <div class="mt-4">
                <h4 class="text-sm font-medium text-gray-700 mb-2">Selected Files (${files.length})</h4>
                <ul class="max-h-40 overflow-y-auto border rounded-md">
                    ${files.map((file, index) => `
                        <li class="p-2 border-b hover:bg-gray-50 flex items-center ${index === 0 ? 'bg-blue-50' : ''}">
                            <i class="fas fa-image text-gray-400 mr-2"></i>
                            <span class="text-sm truncate flex-1">${file.name}</span>
                            <span class="text-xs text-gray-500 ml-2">${(file.size/1024).toFixed(2)} KB</span>
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    };

    const validateFiles = (files) => {
        if (files.length === 0) {
            showStatus('error', 'Please select at least one file');
            return false;
        }

        if (files.length > 20) {
            showStatus('error', 'Maximum 20 files allowed');
            return false;
        }

        for (const file of files) {
            if (!file.name.toLowerCase().endsWith('.png')) {
                showStatus('error', `Only PNG files are allowed (${file.name})`);
                return false;
            }
            
            if (file.size > 10 * 1024 * 1024) {
                showStatus('error', `File too large (${file.name} - max 10MB)`);
                return false;
            }
        }
        
        return true;
    };

    const constructDownloadUrl = (filePath) => {
        const cleanPath = filePath.replace(/^(https?:\/\/[^/]+)?\/?/, '');
        return `${BACKEND_URL}/${cleanPath}`;
    };

    const handleDownload = async (fileData) => {
        try {
            showStatus('loading', 'Preparing download...');
            
            let filePath = fileData.converted_file_url || fileData.converted_file;
            if (!filePath) throw new Error('No file path available');

            const downloadUrl = constructDownloadUrl(filePath);
            const response = await fetch(downloadUrl, {
                signal: abortController?.signal
            });
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);

            const contentDisposition = response.headers.get('content-disposition');
            let fileName = 'converted.pdf';
            if (contentDisposition) {
                const match = contentDisposition.match(/filename="?(.+?)"?$/);
                if (match) fileName = match[1];
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            
            setTimeout(() => {
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            }, 100);

            showStatus('success', 'Download started!');

        } catch (error) {
            console.error('Download failed:', error);
            showStatus('error', error.name === 'AbortError' ? 'Download timed out' : `Download failed: ${error.message}`);
        }
    };

    const renderResults = (data) => {
        downloadLinkContainer.innerHTML = '';
        
        if (!data) {
            downloadLinkContainer.innerHTML = '<p class="text-gray-500">No conversion results received</p>';
            return;
        }

        downloadLinkContainer.innerHTML = `
            <div class="bg-white p-4 rounded-md shadow-sm">
                <h4 class="text-lg font-medium text-gray-800 mb-2">Conversion Successful!</h4>
                <p class="text-sm text-gray-600 mb-4">
                    Combined ${data.page_count || data.original_files.length} files into one PDF
                </p>
                <button id="download-btn" class="w-full custom-download-btn">
                    <i class="fas fa-download"></i>
                    <span>Download PDF (${data.page_count || data.original_files.length} pages)</span>
                </button>
            </div>
        `;

        document.getElementById('download-btn').addEventListener('click', () => {
            handleDownload(data);
        });
    };

    // Event Listeners
    fileInput.addEventListener('change', (e) => {
        selectedFiles = Array.from(e.target.files);
        if (validateFiles(selectedFiles)) {
            showStatus('info', `${selectedFiles.length} PNG files ready for conversion`);
            renderFilePreviews(selectedFiles);
            currentConversion = null;
            downloadLinkContainer.innerHTML = '';
        } else {
            selectedFiles = [];
            renderFilePreviews([]);
        }
    });

    convertBtn.addEventListener('click', async () => {
        if (selectedFiles.length === 0) {
            showStatus('error', 'Please select at least one PNG file');
            return;
        }

        if (abortController) abortController.abort();
        abortController = new AbortController();
        const timeoutId = setTimeout(() => abortController.abort(), CONVERSION_TIMEOUT);

        convertBtn.disabled = true;
        convertBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Converting...';
        showStatus('loading', `Converting ${selectedFiles.length} PNGs to PDF...`);
        downloadLinkContainer.innerHTML = '';

        try {
            const formData = new FormData();
            selectedFiles.forEach(file => {
                formData.append('files', file);
            });

            const response = await fetch(API_ENDPOINT, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Accept': 'application/json'
                },
                signal: abortController.signal
            });

            clearTimeout(timeoutId);

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || data.message || `Conversion failed with status ${response.status}`);
            }

            currentConversion = data;
            renderResults(data);
            showStatus('success', `Successfully combined ${data.page_count || selectedFiles.length} files into PDF!`);
        } catch (error) {
            clearTimeout(timeoutId);
            showStatus('error', error.name === 'AbortError' ? 'Conversion timed out' : `Conversion failed: ${error.message}`);
        } finally {
            convertBtn.disabled = false;
            convertBtn.innerHTML = '<i class="fas fa-exchange-alt mr-2"></i> Convert to PDF';
            abortController = null;
        }
    });
});