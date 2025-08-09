document.addEventListener('DOMContentLoaded', function() {
    const BACKEND_URL = 'http://127.0.0.1:8000';
    const API_ENDPOINT = `${BACKEND_URL}/api/pdf-to-png/`;
    const CONVERSION_TIMEOUT = 60000;

    // DOM Elements
    const fileInput = document.getElementById('pdf-file');
    const convertBtn = document.getElementById('convert-btn');
    const filePreview = document.getElementById('file-preview');
    const conversionStatus = document.getElementById('conversion-status');
    const downloadLinkContainer = document.getElementById('download-link-container');
    
    // State
    let currentConversion = null;
    let abortController = null;

    // Utility Functions
    const getCookie = (name) => {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [cookieName, cookieValue] = cookie.trim().split('=');
            if (cookieName === name) return decodeURIComponent(cookieValue);
        }
        return null;
    };

    const showStatus = (type, message, details = '') => {
        const statusTypes = {
            info: { bg: 'bg-blue-100', border: 'border-blue-500', text: 'text-blue-700', icon: 'fa-info-circle' },
            success: { bg: 'bg-green-100', border: 'border-green-500', text: 'text-green-700', icon: 'fa-check-circle' },
            error: { bg: 'bg-red-100', border: 'border-red-500', text: 'text-red-700', icon: 'fa-exclamation-circle' },
            loading: { bg: 'bg-blue-100', border: 'border-blue-500', text: 'text-blue-700', icon: 'fa-spinner fa-spin' }
        };
        
        const status = statusTypes[type] || statusTypes.info;
        conversionStatus.innerHTML = `
            <div class="${status.bg} border-l-4 ${status.border} ${status.text} p-4 mb-4">
                <div class="flex items-start">
                    <i class="fas ${status.icon} mt-1 mr-3"></i>
                    <div>
                        <p class="font-medium">${message}</p>
                        ${details ? `<p class="text-sm mt-1">${details}</p>` : ''}
                    </div>
                </div>
            </div>
        `;
    };

    const handleFilePreview = (file) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            filePreview.innerHTML = `
                <div class="pdf-preview-container h-64">
                    <embed src="${e.target.result}#toolbar=0&navpanes=0&scrollbar=0" 
                           type="application/pdf" 
                           width="100%" 
                           height="100%">
                </div>
                <div class="bg-white p-3 rounded-md shadow-sm mt-2">
                    <p class="text-sm font-medium text-gray-700">
                        <i class="fas fa-file-pdf mr-2"></i> ${file.name}
                    </p>
                    <p class="text-xs text-gray-500 mt-1">
                        ${(file.size/1024).toFixed(2)} KB
                    </p>
                </div>
            `;
        };
        reader.onerror = () => {
            filePreview.innerHTML = `
                <div class="text-center py-8">
                    <i class="fas fa-exclamation-triangle text-yellow-500 text-3xl mb-2"></i>
                    <p class="text-gray-700">Could not preview PDF</p>
                </div>
            `;
        };
        reader.readAsDataURL(file);
    };

    const validateFile = (file) => {
        // Check file type
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showStatus('error', 'Invalid file type', 'Please upload a PDF file');
            return false;
        }
        
        // Check file size (20MB max)
        if (file.size > 20 * 1024 * 1024) {
            showStatus('error', 'File too large', 'Maximum file size is 20MB');
            return false;
        }
        
        return true;
    };

    const constructDownloadUrl = (filePath) => {
        // Remove any existing domain or double slashes
        const cleanPath = filePath.replace(/^(https?:\/\/[^/]+)?\/?/, '');
        return `${BACKEND_URL}/${cleanPath}`;
    };

    const handleDownload = async (fileData) => {
        try {
            showStatus('loading', 'Preparing download...');
            
            // Get the correct file path
            let filePath;
            if (fileData.converted_file_url) {
                filePath = fileData.converted_file_url;
            } else if (fileData.converted_file) {
                filePath = fileData.converted_file;
            } else {
                throw new Error('No file path available');
            }

            // Construct proper download URL
            const downloadUrl = constructDownloadUrl(filePath);
            console.log('Download URL:', downloadUrl);

            // Extract filename from path (format: "converted_files/{id}_{original_name}.png")
            let fileName = 'converted.png';
            const pathParts = filePath.split('/');
            if (pathParts.length > 0) {
                const lastPart = pathParts[pathParts.length - 1];
                // Remove the ID prefix (format: "123_filename.png")
                const idSeparatorIndex = lastPart.indexOf('_');
                if (idSeparatorIndex !== -1) {
                    fileName = lastPart.substring(idSeparatorIndex + 1);
                    // Replace .pdf extension with .png if needed
                    fileName = fileName.replace(/\.pdf$/i, '.png');
                } else {
                    fileName = lastPart;
                }
            }

            // Fetch the file
            const response = await fetch(downloadUrl, {
                signal: abortController?.signal
            });
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);

            // Create download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            
            // Cleanup
            setTimeout(() => {
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            }, 100);

            showStatus('success', 'Download started!');

        } catch (error) {
            console.error('Download failed:', error);
            showStatus('error', 
                'Download failed',
                error.name === 'AbortError' ? 'The download timed out' : error.message
            );
        }
    };

    const renderResults = (data) => {
        downloadLinkContainer.innerHTML = '';
        
        // Debug the response
        console.log('Conversion API Response:', data);

        if (!data?.converted_file) {
            downloadLinkContainer.innerHTML = `
                <div class="bg-yellow-50 border-l-4 border-yellow-400 text-yellow-700 p-4">
                    <div class="flex">
                        <div class="flex-shrink-0">
                            <i class="fas fa-exclamation-circle mt-1 mr-3"></i>
                        </div>
                        <div>
                            <p class="font-medium">Conversion completed</p>
                            <p class="text-sm">But no download link was provided</p>
                            ${data?.error ? `<p class="text-xs mt-1">${data.error}</p>` : ''}
                        </div>
                    </div>
                </div>
            `;
            return;
        }

        // Extract display filename
        let displayFilename = 'converted.png';
        if (data.converted_file) {
            const pathParts = data.converted_file.split('/');
            if (pathParts.length > 0) {
                const lastPart = pathParts[pathParts.length - 1];
                const idSeparatorIndex = lastPart.indexOf('_');
                if (idSeparatorIndex !== -1) {
                    displayFilename = lastPart.substring(idSeparatorIndex + 1)
                        .replace(/\.pdf$/i, '.png');
                }
            }
        }

        // Apply the download button with proper filename
        downloadLinkContainer.innerHTML = `
            <button id="download-btn" class="custom-download-btn">
                <i class="fas fa-download mr-2"></i> Download
            </button>
        `;

        // Add download event
        document.getElementById('download-btn').addEventListener('click', () => {
            handleDownload(data);
        });
    };

    // Event Listeners
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            if (validateFile(file)) {
                showStatus('info', 'File ready for conversion');
                handleFilePreview(file);
                currentConversion = null;
                downloadLinkContainer.innerHTML = '';
            } else {
                fileInput.value = ''; // Clear invalid file
            }
        }
    });

    convertBtn.addEventListener('click', async () => {
        if (!fileInput.files.length) {
            showStatus('error', 'No file selected', 'Please choose a PDF file first');
            return;
        }

        // Abort any previous request
        if (abortController) {
            abortController.abort();
        }
        abortController = new AbortController();
        const timeoutId = setTimeout(() => {
            if (abortController) abortController.abort();
        }, CONVERSION_TIMEOUT);

        // Set loading state
        convertBtn.disabled = true;
        convertBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Converting...';
        showStatus('loading', 'Converting your PDF...', 'This may take a moment for larger files');
        downloadLinkContainer.innerHTML = '';

        try {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);

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
                throw new Error(data.error || data.message || `Server responded with ${response.status}`);
            }

            if (!data.converted_file) {
                throw new Error('Conversion succeeded but no file URL was returned');
            }

            currentConversion = data;
            renderResults(data);
            showStatus('success', 'Conversion successful!', 'Your PNG file is ready');
        } catch (error) {
            clearTimeout(timeoutId);
            console.error('Conversion error:', error);
            
            let errorMessage = 'Conversion failed';
            let errorDetails = error.message;
            
            if (error.name === 'AbortError') {
                errorMessage = 'Conversion timed out';
                errorDetails = 'The operation took too long. Please try again with a smaller file.';
            } else if (error.message.includes('Failed to fetch')) {
                errorDetails = 'Network error. Please check your internet connection.';
            }

            showStatus('error', errorMessage, errorDetails);
            downloadLinkContainer.innerHTML = '';
        } finally {
            convertBtn.disabled = false;
            convertBtn.innerHTML = '<i class="fas fa-exchange-alt mr-2"></i> Convert to PNG';
            abortController = null;
        }
    });
});