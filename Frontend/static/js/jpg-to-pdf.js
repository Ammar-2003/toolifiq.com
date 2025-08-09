document.addEventListener('DOMContentLoaded', function() {
    // Configuration - Set your backend URL here
    const BACKEND_URL = 'http://127.0.0.1:8000'; // Make sure this matches your Django server
    const API_ENDPOINT = `${BACKEND_URL}/api/jpg-to-pdf/`;

    // DOM Elements
    const fileInput = document.getElementById('jpg-file');
    const convertBtn = document.getElementById('convert-btn');
    const filePreview = document.getElementById('file-preview');
    const conversionStatus = document.getElementById('conversion-status');
    const downloadLinkContainer = document.getElementById('download-link-container');
    
    // State
    let currentConversion = null;

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

    const handleFilePreview = (files) => {
        if (files.length === 1) {
            // Single file preview
            const file = files[0];
            const reader = new FileReader();
            reader.onload = (e) => {
                filePreview.innerHTML = `
                    <div class="mb-4">
                        <img src="${e.target.result}" class="max-w-full max-h-64 rounded-md shadow-sm">
                    </div>
                    <div class="bg-white p-3 rounded-md shadow-sm">
                        <p class="text-sm font-medium text-gray-700">
                            <i class="fas fa-file-alt mr-2"></i> ${file.name}
                        </p>
                        <p class="text-xs text-gray-500 mt-1">
                            <i class="fas fa-info-circle mr-2"></i> ${(file.size/1024).toFixed(2)} KB
                        </p>
                    </div>
                `;
            };
            reader.readAsDataURL(file);
        } else {
            // Multiple files preview
            let totalSize = 0;
            let previewHTML = `
                <div class="mb-4">
                    <div class="grid grid-cols-3 gap-2">
            `;
            
            const readers = [];
            let filesProcessed = 0;
            
            Array.from(files).forEach((file, index) => {
                totalSize += file.size;
                const reader = new FileReader();
                readers.push(reader);
                
                reader.onload = (e) => {
                    previewHTML += `
                        <div class="border rounded p-1">
                            <img src="${e.target.result}" class="w-full h-24 object-cover rounded-sm">
                            <p class="text-xs truncate mt-1">${file.name}</p>
                        </div>
                    `;
                    
                    filesProcessed++;
                    if (filesProcessed === files.length) {
                        previewHTML += `
                            </div>
                        </div>
                        <div class="bg-white p-3 rounded-md shadow-sm">
                            <p class="text-sm font-medium text-gray-700">
                                <i class="fas fa-file-alt mr-2"></i> ${files.length} files selected
                            </p>
                            <p class="text-xs text-gray-500 mt-1">
                                <i class="fas fa-info-circle mr-2"></i> ${(totalSize/1024).toFixed(2)} KB total
                            </p>
                        </div>
                        `;
                        filePreview.innerHTML = previewHTML;
                    }
                };
                reader.readAsDataURL(file);
            });
        }
    };

    const validateFiles = (files) => {
        const validExtensions = /\.jpe?g$/i;
        const validTypes = ['image/jpeg', 'image/jpg'];
        let totalSize = 0;
        
        for (let file of files) {
            if (!validTypes.includes(file.type) && !validExtensions.test(file.name)) {
                showStatus('error', 'Only JPG/JPEG files are allowed');
                fileInput.value = '';
                return false;
            }
            
            if (file.size > 20 * 1024 * 1024) { // 10MB limit per file
                showStatus('error', `File ${file.name} is too large (max 20MB)`);
                fileInput.value = '';
                return false;
            }
            
            totalSize += file.size;
        }
        
        if (totalSize > 100 * 1024 * 1024) { // 50MB total limit
            showStatus('error', 'Total files size too large (max 50MB)');
            fileInput.value = '';
            return false;
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
            
            let filePath;
            if (fileData.converted_file_url) {
                filePath = fileData.converted_file_url;
            } else if (fileData.converted_file) {
                filePath = fileData.converted_file;
            } else {
                throw new Error('No file path available');
            }

            const downloadUrl = constructDownloadUrl(filePath);
            console.log('Download URL:', downloadUrl);

            let fileName = 'converted.pdf';
            const pathParts = filePath.split('/');
            if (pathParts.length > 0) {
                const lastPart = pathParts[pathParts.length - 1];
                const idSeparatorIndex = lastPart.indexOf('_');
                if (idSeparatorIndex !== -1) {
                    fileName = lastPart.substring(idSeparatorIndex + 1);
                } else {
                    fileName = lastPart;
                }
            }

            const response = await fetch(downloadUrl);
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);

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
            showStatus('error', `Download failed: ${error.message}`);
        }
    };

    // Event Listeners
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            const files = Array.from(e.target.files);
            if (validateFiles(files)) {
                showStatus('info', files.length > 1 ? 
                    `${files.length} files ready for conversion` : 
                    'File ready for conversion');
                handleFilePreview(files);
                currentConversion = null;
            }
        }
    });

    convertBtn.addEventListener('click', async () => {
        if (!fileInput.files || fileInput.files.length === 0) {
            showStatus('error', 'Please select at least one file first');
            return;
        }

        convertBtn.disabled = true;
        convertBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Converting...';
        showStatus('loading', 'Converting files...');
        downloadLinkContainer.innerHTML = '';

        try {
            const formData = new FormData();
            Array.from(fileInput.files).forEach((file, index) => {
                formData.append('files', file);
            });

            const response = await fetch(API_ENDPOINT, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.error || 'Conversion failed');
            }

            const data = await response.json();
            currentConversion = data;

            const convertedFilename = data.converted_file.split('/').pop().split('_').slice(1).join('_');
            downloadLinkContainer.innerHTML = `
                <button id="download-btn" class="custom-download-btn">
                    <i class="fas fa-download"></i>
                    <span>Download PDF (${data.original_files.length} pages)</span>
                </button>
            `;

            document.getElementById('download-btn').addEventListener('click', () => {
                handleDownload(currentConversion);
            });

            showStatus('success', 'Conversion successful! Files combined into single PDF.');

        } catch (error) {
            console.error('Conversion error:', error);
            showStatus('error', error.message);
        } finally {
            convertBtn.disabled = false;
            convertBtn.innerHTML = '<i class="fas fa-exchange-alt mr-2"></i> Convert to PDF';
        }
    });
});