// Global configuration object to store user preferences
let userConfig = {};

// Store game data for details functionality
let widgetGameData = {};

// Game modal functionality
let gameModal = null;

// Security: XSS Protection Functions
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') {
        return unsafe;
    }
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function sanitizeText(text) {
    // Remove any script tags or dangerous content
    if (typeof text !== 'string') {
        return text;
    }
    return text.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
}

// Initialize the dashboard when page loads
document.addEventListener('DOMContentLoaded', function() {
    loadUserConfig();
    addTeamSearch();
    makeWidgetsClickable();
});

// Load user configuration from cookies
function loadUserConfig() {
    fetch('/load_config')
        .then(response => response.json())
        .then(config => {
            userConfig = config;
            // Restore user's previous selections
            for (let widgetId in config) {
                const widgetIndex = parseInt(widgetId.split('_')[1]);
                const widget = config[widgetId];
                
                // Set the sport dropdown
                const sportSelect = document.querySelector(`[data-widget="${widgetIndex}"].sport-select`);
                if (sportSelect && widget.sport) {
                    sportSelect.value = widget.sport;
                    onSportChange(widgetIndex);
                    
                    // Set the team dropdown after a short delay to allow teams to load
                    setTimeout(() => {
                        const teamSelect = document.querySelector(`[data-widget="${widgetIndex}"].team-select`);
                        if (teamSelect && widget.team) {
                            teamSelect.value = widget.team;
                            onTeamChange(widgetIndex);
                        }
                    }, 500);
                }
            }
        })
        .catch(error => {
            console.error('Error loading config:', error);
        });
}

// Save user configuration to cookies
function saveUserConfig() {
    fetch('/save_config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(userConfig)
    })
    .then(response => response.json())
    .then(data => {
        console.log('Configuration saved:', data);
    })
    .catch(error => {
        console.error('Error saving config:', error);
    });
}

// Handle sport selection change
function onSportChange(widgetIndex) {
    const sportSelect = document.querySelector(`[data-widget="${widgetIndex}"].sport-select`);
    const teamSelect = document.querySelector(`[data-widget="${widgetIndex}"].team-select`);
    const sport = sportSelect.value;
    
    console.log(`Sport changed to: ${sport} for widget ${widgetIndex}`);
    
    if (sport) {
        // Enable team dropdown and load teams
        teamSelect.disabled = false;
        teamSelect.innerHTML = '<option value="">Loading teams...</option>';
        
        // Fetch teams for the selected sport
        fetch(`/api/teams/${encodeURIComponent(sport)}`)
            .then(response => {
                console.log(`API response status: ${response.status}`);
                return response.json();
            })
            .then(teams => {
                console.log(`Received ${teams.length} teams:`, teams);
                teamSelect.innerHTML = '<option value="">Select a team</option>';
                teams.forEach(team => {
                    const option = document.createElement('option');
                    option.value = team;
                    option.textContent = team;
                    teamSelect.appendChild(option);
                });
            })
            .catch(error => {
                console.error('Error fetching teams:', error);
                teamSelect.innerHTML = '<option value="">Error loading teams</option>';
            });
    } else {
        // Disable team dropdown if no sport selected
        teamSelect.disabled = true;
        teamSelect.innerHTML = '<option value="">Choose sport first</option>';
        
        // Hide score display and show config
        const widget = document.getElementById(`widget-${widgetIndex}`);
        const configMode = widget.querySelector('.config-mode');
        const scoreDisplay = widget.querySelector('.score-display');
        configMode.style.display = 'block';
        scoreDisplay.style.display = 'none';
        
        // Remove from user config
        delete userConfig[`widget_${widgetIndex}`];
        saveUserConfig();
    }
}

// Handle team selection change
function onTeamChange(widgetIndex) {
    const sportSelect = document.querySelector(`[data-widget="${widgetIndex}"].sport-select`);
    const teamSelect = document.querySelector(`[data-widget="${widgetIndex}"].team-select`);
    const sport = sportSelect.value;
    const team = teamSelect.value;
    
    if (sport && team) {
        // Save configuration
        userConfig[`widget_${widgetIndex}`] = { sport: sport, team: team };
        saveUserConfig();
        
        // Switch to score display mode
        showScoreDisplay(widgetIndex);
        
        // Fetch and display scores
        fetchScores(widgetIndex, sport, team);
    }
}

// Show score display and hide configuration
function showScoreDisplay(widgetIndex) {
    const widget = document.getElementById(`widget-${widgetIndex}`);
    const configMode = widget.querySelector('.config-mode');
    const scoreDisplay = widget.querySelector('.score-display');
    
    configMode.style.display = 'none';
    scoreDisplay.style.display = 'block';
}

// Fetch scores for a specific widget
function fetchScores(widgetIndex, sport, team) {
    const widget = document.getElementById(`widget-${widgetIndex}`);
    widget.classList.add('loading');
    
    fetch(`/api/scores/${sport}/${team}`)
        .then(response => response.json())
        .then(data => {
            widget.classList.remove('loading');
            
            if (data.error) {
                console.error('Error fetching scores:', data.error);
                updateScoreDisplay(widgetIndex, {
                    team: team,
                    team_score: 'N/A',
                    opponent: 'Error loading data',
                    opponent_score: 'N/A',
                    status: 'Error',
                    last_updated: new Date().toLocaleTimeString(),
                    venue: 'N/A'
                });
            } else {
                updateScoreDisplay(widgetIndex, data);
            }
        })
        .catch(error => {
            widget.classList.remove('loading');
            console.error('Error fetching scores:', error);
            updateScoreDisplay(widgetIndex, {
                team: team,
                team_score: 'N/A',
                opponent: 'Connection error',
                opponent_score: 'N/A',
                status: 'Error',
                last_updated: new Date().toLocaleTimeString(),
                venue: 'N/A'
            });
        });
}

// Get appropriate emoji based on game status
function getStatusEmoji(status) {
    const statusLower = status.toLowerCase();
    if (statusLower.includes('final')) return '✅';
    if (statusLower.includes('progress') || statusLower.includes('live')) return '🔴';
    if (statusLower.includes('halftime') || statusLower.includes('intermission')) return '⏸️';
    if (statusLower.includes('delayed')) return '⏳';
    if (statusLower.includes('postponed')) return '⏱️';
    if (statusLower.includes('canceled')) return '❌';
    return '📅'; // scheduled/upcoming
}

// Format game status for better display
function formatGameStatus(status, venue) {
    const emoji = getStatusEmoji(status);
    let displayStatus = status;
    
    // Simplify common status messages
    if (status.includes('Final')) {
        displayStatus = 'FINAL';
    } else if (status.includes('In Progress')) {
        displayStatus = 'LIVE';
    } else if (status.includes('Halftime')) {
        displayStatus = 'HALFTIME';
    } else if (status.includes('Scheduled')) {
        displayStatus = 'UPCOMING';
    }
    
    return `${emoji} ${displayStatus}`;
}

// Format date for next game display
function formatGameDate(dateString) {
    const gameDate = new Date(dateString);
    const now = new Date();
    
    // Calculate difference in days more accurately
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const gameDateStart = new Date(gameDate.getFullYear(), gameDate.getMonth(), gameDate.getDate());
    const diffDays = Math.round((gameDateStart - todayStart) / (1000 * 60 * 60 * 24));
    
    const timeOptions = { 
        hour: 'numeric', 
        minute: '2-digit', 
        hour12: true 
    };
    
    const dateTimeOptions = { 
        weekday: 'short', 
        month: 'short', 
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    };
    
    if (diffDays === 0) {
        return `Today at ${gameDate.toLocaleTimeString('en-US', timeOptions)}`;
    } else if (diffDays === 1) {
        return `Tomorrow at ${gameDate.toLocaleTimeString('en-US', timeOptions)}`;
    } else if (diffDays === -1) {
        return `Yesterday at ${gameDate.toLocaleTimeString('en-US', timeOptions)}`;
    } else if (diffDays <= 7 && diffDays > 1) {
        return gameDate.toLocaleDateString('en-US', { weekday: 'long', hour: 'numeric', minute: '2-digit', hour12: true });
    } else {
        return gameDate.toLocaleDateString('en-US', dateTimeOptions);
    }
}

// Update score display with new data including next game
function updateScoreDisplay(widgetIndex, data) {
    // Store game data for details functionality
    widgetGameData[widgetIndex] = data;
    
    const widget = document.getElementById(`widget-${widgetIndex}`);
    const isUpcoming = data.status_type === 'STATUS_SCHEDULED' && data.team_score === '-';
    
    if (isUpcoming) {
        // For upcoming games, show minimal display
        // Security: Use textContent (not innerHTML) to prevent XSS
        document.getElementById(`team-name-${widgetIndex}`).textContent = sanitizeText(data.team);
        document.getElementById(`team-score-${widgetIndex}`).style.display = 'none';
        document.getElementById(`opponent-name-${widgetIndex}`).textContent = sanitizeText(data.opponent);
        document.getElementById(`opponent-score-${widgetIndex}`).style.display = 'none';
        
        // Show game time instead of scores
        const vsElement = widget.querySelector('.vs');
        const gameTime = formatGameDate(data.game_date_iso);
        vsElement.textContent = gameTime;
        vsElement.style.fontSize = '0.8rem';
        vsElement.style.color = '#42A5F5';
        vsElement.style.fontWeight = '600';
    } else {
        // For completed/in-progress games, show scores normally
        // Security: Use textContent (not innerHTML) to prevent XSS
        document.getElementById(`team-name-${widgetIndex}`).textContent = sanitizeText(data.team);
        document.getElementById(`team-score-${widgetIndex}`).textContent = sanitizeText(data.team_score);
        document.getElementById(`team-score-${widgetIndex}`).style.display = 'block';
        document.getElementById(`opponent-name-${widgetIndex}`).textContent = sanitizeText(data.opponent);
        document.getElementById(`opponent-score-${widgetIndex}`).textContent = sanitizeText(data.opponent_score);
        document.getElementById(`opponent-score-${widgetIndex}`).style.display = 'block';
        
        // Reset VS styling
        const vsElement = widget.querySelector('.vs');
        vsElement.textContent = 'VS';
        vsElement.style.fontSize = '0.75rem';
        vsElement.style.color = 'rgba(255, 255, 255, 0.5)';
        vsElement.style.fontWeight = '600';
    }
    
    // Enhanced status display with emoji
    const statusElement = document.getElementById(`status-${widgetIndex}`);
    const formattedStatus = formatGameStatus(data.status, data.venue);
    statusElement.innerHTML = formattedStatus;
    
    // Add venue information if available
    const venueElement = document.getElementById(`venue-${widgetIndex}`);
    if (data.venue && data.venue !== 'TBD' && data.venue !== 'N/A' && data.venue !== '-') {
        // Security: Use textContent to prevent XSS
        venueElement.textContent = `📍 ${sanitizeText(data.venue)}`;
        venueElement.style.display = 'block';
    } else {
        venueElement.style.display = 'none';
    }

    // Display next game information (only if primary game is completed/in-progress)
    const nextGameElement = document.getElementById(`next-game-${widgetIndex}`);
    if (data.next_game && nextGameElement && !isUpcoming) {
        const nextGame = data.next_game;
        const formattedDate = formatGameDate(nextGame.game_date);
        // Security: Escape HTML before using innerHTML
        nextGameElement.innerHTML = `
            <div class="next-game-label">Next:</div>
            <div class="next-game-details">vs ${escapeHtml(sanitizeText(nextGame.opponent))} • ${escapeHtml(formattedDate)}</div>
        `;
        nextGameElement.style.display = 'block';
    } else if (nextGameElement) {
        nextGameElement.style.display = 'none';
    }
    
    document.getElementById(`updated-${widgetIndex}`).textContent = `Updated: ${data.last_updated}`;
    
    // Add visual feedback for live games
    if (data.status.toLowerCase().includes('progress') || data.status.toLowerCase().includes('live')) {
        widget.classList.add('live-game');
    } else {
        widget.classList.remove('live-game');
    }
    
    // Show/hide details button based on whether game data is available
    const detailsBtn = widget.querySelector('.details-btn');
    if (data.opponent && data.opponent !== 'No games found' && data.opponent !== 'Error loading data' && data.opponent !== 'Connection error') {
        detailsBtn.style.display = 'flex';
    } else {
        detailsBtn.style.display = 'none';
    }
}

// Refresh all scores (Check In button functionality)
function refreshScores() {
    const button = document.getElementById('refresh-btn');
    const originalText = button.innerHTML;
    
    // Show loading state
    button.innerHTML = '<span class="refresh-icon">🔄</span> Refreshing...';
    button.disabled = true;
    
    let refreshPromises = [];
    
    // Refresh all configured widgets
    for (let widgetId in userConfig) {
        const widgetIndex = parseInt(widgetId.split('_')[1]);
        const widget = userConfig[widgetId];
        
        if (widget.sport && widget.team) {
            const promise = new Promise((resolve) => {
                fetchScores(widgetIndex, widget.sport, widget.team);
                setTimeout(resolve, 1000); // Ensure minimum loading time for UX
            });
            refreshPromises.push(promise);
        }
    }
    
    // Wait for all refreshes to complete
    Promise.all(refreshPromises).then(() => {
        button.innerHTML = originalText;
        button.disabled = false;
        
        // Show success feedback
        button.innerHTML = '<span class="refresh-icon">✅</span> Updated!';
        setTimeout(() => {
            button.innerHTML = originalText;
        }, 2000);
    });
}

// Reset all widgets to configuration mode
function resetAllWidgets() {
    if (confirm('Are you sure you want to reset all widgets? This will clear your saved configuration.')) {
        userConfig = {};
        saveUserConfig();
        
        // Reset all widgets (now only 4 widgets)
        for (let i = 0; i < 4; i++) {
            const widget = document.getElementById(`widget-${i}`);
            const configMode = widget.querySelector('.config-mode');
            const scoreDisplay = widget.querySelector('.score-display');
            const sportSelect = widget.querySelector('.sport-select');
            const teamSelect = widget.querySelector('.team-select');
            
            // Reset dropdowns
            sportSelect.value = '';
            teamSelect.value = '';
            teamSelect.disabled = true;
            teamSelect.innerHTML = '<option value="">Choose sport first</option>';
            
            // Show config mode
            configMode.style.display = 'block';
            scoreDisplay.style.display = 'none';
            
            // Remove loading and live states
            widget.classList.remove('loading', 'live-game');
        }
        
        // Show success message
        const resetBtn = document.querySelector('.reset-btn');
        const originalText = resetBtn.innerHTML;
        resetBtn.innerHTML = '<span>✅</span> Reset Complete';
        setTimeout(() => {
            resetBtn.innerHTML = originalText;
        }, 2000);
    }
}

// Individual widget reconfiguration
function reconfigureWidget(widgetIndex) {
    const widget = document.getElementById(`widget-${widgetIndex}`);
    const configMode = widget.querySelector('.config-mode');
    const scoreDisplay = widget.querySelector('.score-display');
    const sportSelect = widget.querySelector('.sport-select');
    const teamSelect = widget.querySelector('.team-select');
    
    // Reset dropdowns
    sportSelect.value = '';
    teamSelect.value = '';
    teamSelect.disabled = true;
    teamSelect.innerHTML = '<option value="">Choose sport first</option>';
    
    // Show config mode
    configMode.style.display = 'block';
    scoreDisplay.style.display = 'none';
    
    // Remove from user config
    delete userConfig[`widget_${widgetIndex}`];
    saveUserConfig();
    
    // Remove loading and live states
    widget.classList.remove('loading', 'live-game');
}

// Enhanced search functionality for team dropdowns
function addTeamSearch() {
    const teamSelects = document.querySelectorAll('.team-select');
    
    teamSelects.forEach(select => {
        select.addEventListener('focus', function() {
            // Add search functionality when focused
            this.setAttribute('data-original-size', this.size);
            if (this.options.length > 10) {
                this.size = Math.min(10, this.options.length);
            }
        });
        
        select.addEventListener('blur', function() {
            // Reset size when focus lost
            this.size = this.getAttribute('data-original-size') || 1;
        });
    });
}

// Make widgets clickable to open modal
function makeWidgetsClickable() {
    for (let i = 0; i < 4; i++) {
        const widget = document.getElementById(`widget-${i}`);
        const scoreDisplay = widget.querySelector('.score-display');
        
        scoreDisplay.addEventListener('click', function(e) {
            // Don't trigger if clicking on action buttons
            if (e.target.closest('.widget-actions')) {
                return;
            }
            
            // Only open details if there's valid game data
            const gameData = widgetGameData[i];
            if (gameData && gameData.opponent !== 'No games found' && gameData.opponent !== 'Error loading data') {
                openGameModal(i);
            }
        });
        
        // Add hover effect to show it's clickable
        scoreDisplay.addEventListener('mouseenter', function() {
            if (widgetGameData[i] && widgetGameData[i].opponent !== 'No games found') {
                this.style.cursor = 'pointer';
                this.style.transform = 'scale(1.02)';
                this.style.transition = 'transform 0.2s ease';
            }
        });
        
        scoreDisplay.addEventListener('mouseleave', function() {
            this.style.cursor = 'default';
            this.style.transform = 'scale(1)';
        });
    }
}

// Enhanced game details with modal functionality
function openGameDetails(widgetIndex) {
    const gameData = widgetGameData[widgetIndex];
    
    if (!gameData || gameData.opponent === 'No games found') {
        return;
    }

    // Open the modal instead of Google search
    openGameModal(widgetIndex);
}

function createGameModal() {
    if (gameModal) return; // Already created
    
    // Create modal HTML
    const modalHTML = `
        <div id="gameModal" class="game-modal">
            <div class="game-modal-content">
                <span class="game-modal-close">&times;</span>
                <div id="gameModalContent">
                    <div class="loading-spinner">
                        <div class="spinner-icon">🏀</div>
                        <p>Loading game details...</p>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Add to document
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    gameModal = document.getElementById('gameModal');
    const closeBtn = document.querySelector('.game-modal-close');
    
    // Event listeners
    closeBtn.onclick = closeGameModal;
    
    gameModal.onclick = function(event) {
        if (event.target === gameModal) {
            closeGameModal();
        }
    };
    
    // ESC key to close
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && gameModal && gameModal.style.display === 'block') {
            closeGameModal();
        }
    });
}

function openGameModal(widgetIndex) {
    createGameModal();
    gameModal.style.display = 'block';
    loadGameDetails(widgetIndex);
}

function closeGameModal() {
    if (gameModal) {
        gameModal.style.display = 'none';
    }
}

function generateLeadersDisplay(leaders) {
    console.log('=== LEADERS DISPLAY DEBUG ===');
    console.log('Leaders data received:', leaders);
    console.log('Type:', typeof leaders);
    console.log('Is Array:', Array.isArray(leaders));
    console.log('Keys:', Object.keys(leaders || {}));
    
    if (!leaders || typeof leaders !== 'object' || Object.keys(leaders).length === 0) {
        console.log('No leaders data available - returning fallback message');
        return '<p>No game leaders data available</p>';
    }
    
    const leaderEntries = Object.entries(leaders);
    console.log('Leader entries:', leaderEntries);
    
    if (leaderEntries.length === 0) {
        return '<p>No statistical leaders found</p>';
    }
    
    // Filter out empty or invalid categories
    const validEntries = leaderEntries.filter(([category, categoryLeaders]) => {
        console.log(`Checking category "${category}":`, categoryLeaders);
        
        if (!Array.isArray(categoryLeaders)) {
            console.log(`  - Not an array, skipping`);
            return false;
        }
        
        if (categoryLeaders.length === 0) {
            console.log(`  - Empty array, skipping`);
            return false;
        }
        
        // Check if any leaders have valid data
        const hasValidData = categoryLeaders.some(leader => {
            const hasName = leader.name && leader.name !== 'Unknown' && leader.name !== 'Unknown Player';
            const hasValue = leader.value && leader.value !== '0';
            console.log(`    - Leader check: name="${leader.name}", value="${leader.value}", valid=${hasName && hasValue}`);
            return hasName && hasValue;
        });
        
        console.log(`  - Category "${category}" has valid data: ${hasValidData}`);
        return hasValidData;
    });
    
    console.log('Valid entries after filtering:', validEntries.map(([cat, leaders]) => `${cat} (${leaders.length})`));
    
    if (validEntries.length === 0) {
        return `
            <div class="no-leaders-message">
                <p>📊 Detailed player statistics not available</p>
                <p style="font-size: 0.8rem; color: rgba(255,255,255,0.5); margin-top: 0.5rem;">
                    Game leaders data may not be available for this game type or timing
                </p>
            </div>
        `;
    }
    
    return validEntries.slice(0, 6).map(([category, categoryLeaders]) => {
        console.log(`Rendering category: ${category}`, categoryLeaders);
        
        // Filter and clean the leaders for this category
        const cleanLeaders = categoryLeaders
            .filter(leader => {
                const isValid = leader.name && 
                              leader.name !== 'Unknown' && 
                              leader.name !== 'Unknown Player' &&
                              leader.value && 
                              leader.value !== '0';
                console.log(`    - Leader "${leader.name}" valid: ${isValid}`);
                return isValid;
            })
            .slice(0, 3); // Top 3 leaders per category
        
        if (cleanLeaders.length === 0) {
            return `
                <div class="leader-category">
                    <div class="category-title">${category}</div>
                    <div class="leader-item">
                        <span class="leader-name">No data available</span>
                    </div>
                </div>
            `;
        }
        
        return `
            <div class="leader-category">
                <div class="category-title">${category}</div>
                ${cleanLeaders.map((leader, index) => {
                    console.log(`      - Rendering leader ${index}:`, leader);
                    return `
                        <div class="leader-item">
                            <span class="leader-name">${leader.name || 'Unknown'}</span>
                            <span class="leader-team">${leader.team || ''}</span>
                            <span class="leader-value">${leader.value || '0'}</span>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    }).join('');
}

// Enhanced loadGameDetails function with better error handling
async function loadGameDetails(widgetIndex) {
    const gameData = widgetGameData[widgetIndex];
    const sport = userConfig[`widget_${widgetIndex}`]?.sport;
    const team = userConfig[`widget_${widgetIndex}`]?.team;
    const modalContent = document.getElementById('gameModalContent');
    
    console.log(`=== LOADING GAME DETAILS ===`);
    console.log(`Widget: ${widgetIndex}, Sport: ${sport}, Team: ${team}`);
    
    try {
        // Show loading state
        modalContent.innerHTML = `
            <div class="loading-spinner">
                <div class="spinner-icon">${getSportEmoji(sport)}</div>
                <p>Loading detailed game data...</p>
                <div class="loading-progress"></div>
            </div>
        `;

        // Fetch detailed game data from your API endpoint
        const response = await fetch(`/api/game-details/${encodeURIComponent(sport)}/${encodeURIComponent(team)}`);
        const detailedData = await response.json();
        
        console.log('Detailed data response:', detailedData);
        
        if (detailedData.error) {
            throw new Error(detailedData.error);
        }
        
        // Check what data we actually received
        console.log('Detailed data structure:');
        console.log('- Box score:', detailedData.box_score?.length || 0, 'teams');
        console.log('- Leaders:', Object.keys(detailedData.leaders || {}).length, 'categories');
        console.log('- Leaders data:', detailedData.leaders);
        
        displayDetailedGameData(detailedData, sport, widgetIndex);

    } catch (error) {
        console.error('Error loading detailed game data:', error);
        
        // Enhanced fallback with more debugging info
        modalContent.innerHTML = `
            <div class="error-fallback">
                <div class="fallback-header">
                    <h3>⚠️ Detailed Data Unavailable</h3>
                    <p>Showing basic game information</p>
                    <p style="font-size: 0.8rem; color: rgba(255,255,255,0.5);">
                        Error: ${error.message}
                    </p>
                </div>
                <div id="fallbackContent"></div>
            </div>
        `;
        
        // Show basic game data in a nice format
        setTimeout(() => {
            const fallbackContent = document.getElementById('fallbackContent');
            if (fallbackContent) {
                displayBasicGameData(gameData, sport, widgetIndex, fallbackContent);
            }
        }, 100);
    }
}

function getSportEmoji(sport) {
    const emojis = {
        'nba': '🏀',
        'wnba': '🏀',
        'nfl': '🏈',
        'mlb': '⚾',
        'nhl': '🏒',
        'mls': '⚽',
        'premier league': '⚽',
        'la liga': '⚽'
    };
    return emojis[sport?.toLowerCase()] || '🏀';
}

function displayDetailedGameData(detailedData, sport, widgetIndex) {
    const modalContent = document.getElementById('gameModalContent');
    const isCompleted = detailedData.status?.completed || false;
    const isLive = detailedData.status?.state === 'STATUS_IN_PROGRESS' || detailedData.status?.state === 'STATUS_HALFTIME';
    
    // Format game date
    let gameDateTime = 'Unknown';
    if (detailedData.date) {
        try {
            const date = new Date(detailedData.date);
            gameDateTime = date.toLocaleDateString('en-US', { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
            });
        } catch (e) {
            gameDateTime = 'Date unavailable';
        }
    }
    
    modalContent.innerHTML = `
        <div class="detailed-game-header">
            <div class="game-matchup-detailed">
                ${detailedData.away_team.name} @ ${detailedData.home_team.name}
            </div>
            <div class="game-status-badge ${isLive ? 'live' : isCompleted ? 'final' : 'upcoming'}">
                ${isLive ? '🔴 LIVE' : isCompleted ? '✅ FINAL' : '📅 SCHEDULED'}
                ${detailedData.status?.clock ? ` • ${detailedData.status.clock}` : ''}
                ${detailedData.status?.period > 0 ? ` • Period ${detailedData.status.period}` : ''}
            </div>
            <div class="game-meta">
                ${gameDateTime}<br>
                ${detailedData.venue?.name ? `📍 ${detailedData.venue.name}` : ''}
                ${detailedData.venue?.city ? `, ${detailedData.venue.city}` : ''}
            </div>
        </div>

        <div class="team-matchup-section">
            <div class="team-display">
                <div class="team-card away-team">
                    ${detailedData.away_team.logo ? `<img src="${detailedData.away_team.logo}" alt="${detailedData.away_team.name}" class="team-logo">` : ''}
                    <div class="team-info-detailed">
                        <div class="team-name-detailed">${detailedData.away_team.name}</div>
                        <div class="team-record">${detailedData.away_team.short_name}</div>
                    </div>
                    <div class="team-score-detailed">${detailedData.away_team.score}</div>
                </div>
                
                <div class="vs-divider">VS</div>
                
                <div class="team-card home-team">
                    ${detailedData.home_team.logo ? `<img src="${detailedData.home_team.logo}" alt="${detailedData.home_team.name}" class="team-logo">` : ''}
                    <div class="team-info-detailed">
                        <div class="team-name-detailed">${detailedData.home_team.name}</div>
                        <div class="team-record">${detailedData.home_team.short_name}</div>
                    </div>
                    <div class="team-score-detailed">${detailedData.home_team.score}</div>
                </div>
            </div>
        </div>

        ${detailedData.box_score && detailedData.box_score.length > 0 ? `
            <div class="stats-section">
                <div class="stats-title">📊 Team Statistics</div>
                <div class="team-stats-grid">
                    ${generateTeamStatsComparison(detailedData.box_score)}
                </div>
            </div>
        ` : ''}

        ${detailedData.leaders && Object.keys(detailedData.leaders).length > 0 ? `
            <div class="stats-section">
                <div class="stats-title">⭐ Game Leaders</div>
                <div class="leaders-grid">
                    ${generateLeadersDisplay(detailedData.leaders)}
                </div>
            </div>
        ` : `
            <div class="stats-section">
                <div class="stats-title">⭐ Game Leaders</div>
                <p>No game leaders data available</p>
            </div>
        `}

        ${detailedData.scoring_summary && detailedData.scoring_summary.length > 0 ? `
            <div class="stats-section">
                <div class="stats-title">🎯 Scoring Summary</div>
                <div class="scoring-timeline">
                    ${generateScoringTimeline(detailedData.scoring_summary)}
                </div>
            </div>
        ` : ''}

        <div class="modal-actions">
            <button onclick="searchForMoreDetails('${detailedData.away_team.name}', '${detailedData.home_team.name}', '${sport}', '${detailedData.status?.display}')" 
                    class="action-btn primary-btn">
                🔍 Search More Details
            </button>
            <button onclick="searchForTeamStats('${detailedData.home_team.name}', '${sport}')" 
                    class="action-btn secondary-btn">
                📊 Team Season Stats
            </button>
            <button onclick="shareGameResult('${detailedData.away_team.name}', '${detailedData.home_team.name}', '${detailedData.away_team.score}', '${detailedData.home_team.score}')" 
                    class="action-btn share-btn">
                📤 Share Result
            </button>
        </div>

        <div class="modal-footer">
            <div class="data-source">Data from ESPN • Real-time updates</div>
        </div>
    `;
}

function generateTeamStatsComparison(boxScore) {
    if (!boxScore || boxScore.length < 2) return '<p>No team statistics available</p>';
    
    const team1 = boxScore[0];
    const team2 = boxScore[1];
    
    // Clean up and organize statistics
    const team1Stats = cleanAndFilterStats(team1.statistics);
    const team2Stats = cleanAndFilterStats(team2.statistics);
    
    if (team1Stats.length === 0 && team2Stats.length === 0) {
        return '<p>No detailed statistics available</p>';
    }
    
    // Create maps for easier lookup
    const team1StatMap = new Map();
    const team2StatMap = new Map();
    
    team1Stats.forEach(stat => {
        team1StatMap.set(stat.name, stat.value);
    });
    
    team2Stats.forEach(stat => {
        team2StatMap.set(stat.name, stat.value);
    });
    
    // Find common stats between both teams for comparison
    const commonStatNames = team1Stats
        .map(s => s.name)
        .filter(name => team2StatMap.has(name))
        .slice(0, 12);
    
    if (commonStatNames.length === 0) {
        return `
            <div class="team-stats-container">
                <div class="team-stats-header">
                    <h4>📊 Individual Team Statistics</h4>
                </div>
                
                <div class="individual-stats-grid">
                    <div class="team-stats-column">
                        <h5>${team1.team_name}</h5>
                        ${team1Stats.slice(0, 8).map(stat => `
                            <div class="stat-row">
                                <span class="stat-name">${stat.name}</span>
                                <span class="stat-value">${stat.value}</span>
                            </div>
                        `).join('')}
                    </div>
                    
                    <div class="team-stats-column">
                        <h5>${team2.team_name}</h5>
                        ${team2Stats.slice(0, 8).map(stat => `
                            <div class="stat-row">
                                <span class="stat-name">${stat.name}</span>
                                <span class="stat-value">${stat.value}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
    }
    
    return `
        <div class="team-stats-container">
            <div class="team-stats-header">
                <h4>📊 Team Statistics Comparison</h4>
            </div>
            
            <div class="stats-comparison-grid">
                <div class="stats-grid-header">
                    <div class="team-name-header">${team1.team_name}</div>
                    <div class="stat-name-header">Statistic</div>
                    <div class="team-name-header">${team2.team_name}</div>
                </div>
                
                ${commonStatNames.map(statName => `
                    <div class="stat-comparison-row">
                        <div class="stat-value-left">${team1StatMap.get(statName) || '0'}</div>
                        <div class="stat-name-center">${statName}</div>
                        <div class="stat-value-right">${team2StatMap.get(statName) || '0'}</div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function cleanAndFilterStats(statistics) {
    if (!statistics || !Array.isArray(statistics)) return [];
    
    return statistics
        .map(stat => ({
            name: cleanStatName(stat.display_name || stat.name),
            value: stat.value || '0'
        }))
        .filter(stat => stat.name && isImportantStat(stat.name))
        .slice(0, 15);
}

function cleanStatName(name) {
    if (!name) return '';
    
    const cleanMap = {
        'fieldGoalsMade-fieldGoalsAttempted': 'Field Goals',
        'threePointFieldGoalsMade-threePointFieldGoalsAttempted': '3-Point Shots',
        'freeThrowsMade-freeThrowsAttempted': 'Free Throws',
        'fieldGoalPct': 'Field Goal %',
        'threePointFieldGoalPct': '3-Point %', 
        'freeThrowPct': 'Free Throw %',
        'totalRebounds': 'Total Rebounds',
        'offensiveRebounds': 'Offensive Rebounds',
        'defensiveRebounds': 'Defensive Rebounds',
        'assists': 'Assists',
        'steals': 'Steals',
        'blocks': 'Blocks',
        'turnovers': 'Turnovers',
        'personalFouls': 'Personal Fouls',
        'points': 'Points'
    };
    
    if (cleanMap[name]) {
        return cleanMap[name];
    }
    
    return name
        .replace(/([A-Z])/g, ' $1')
        .replace(/^./, str => str.toUpperCase())
        .replace(/\s+/g, ' ')
        .trim();
}

function isImportantStat(statName) {
    const importantStats = [
        'Field Goals', 'Field Goal %', '3-Point Shots', '3-Point %', 
        'Free Throws', 'Free Throw %', 'Total Rebounds', 'Assists', 
        'Steals', 'Blocks', 'Turnovers', 'Points', 'Personal Fouls'
    ];
    
    return importantStats.some(important => 
        statName.toLowerCase().includes(important.toLowerCase())
    );
}

function generateScoringTimeline(scoringSummary) {
    return scoringSummary.slice(0, 10).map(play => `
        <div class="scoring-play">
            <div class="play-time">${play.period} ${play.clock}</div>
            <div class="play-team">${play.team}</div>
            <div class="play-description">${play.description}</div>
            <div class="play-points">+${play.score_value}</div>
        </div>
    `).join('');
}

function displayBasicGameData(gameData, sport, widgetIndex, container) {
    const isUpcoming = gameData.status_type === 'STATUS_SCHEDULED' && gameData.team_score === '-';
    const isLive = gameData.status_type === 'STATUS_IN_PROGRESS' || gameData.status_type === 'STATUS_HALFTIME';
    
    container.innerHTML = `
        <div class="basic-game-display">
            <div class="basic-matchup">
                <div class="basic-team">
                    <span class="team-name">${gameData.team}</span>
                    <span class="team-score">${gameData.team_score}</span>
                </div>
                <div class="basic-vs">vs</div>
                <div class="basic-team">
                    <span class="team-name">${gameData.opponent}</span>
                    <span class="team-score">${gameData.opponent_score}</span>
                </div>
            </div>
            
            <div class="basic-status ${isLive ? 'live' : ''}">${gameData.status}</div>
            
            ${gameData.venue && gameData.venue !== 'TBD' ? `
                <div class="basic-venue">📍 ${gameData.venue}</div>
            ` : ''}
            
            ${gameData.next_game ? `
                <div class="basic-next-game">
                    <strong>Next:</strong> vs ${gameData.next_game.opponent} • ${formatGameDate(gameData.next_game.game_date)}
                </div>
            ` : ''}
        </div>
        
        <div class="basic-actions">
            <button onclick="searchForMoreDetails('${gameData.team}', '${gameData.opponent}', '${sport}', '${gameData.status}')" 
                    class="action-btn primary-btn">
                🔍 Search Game Details
            </button>
        </div>
    `;
}

function searchForMoreDetails(team, opponent, sport, status) {
    let searchQuery = '';
    
    if (status.toLowerCase().includes('final')) {
        searchQuery = `${team} vs ${opponent} box score ${sport}`;
    } else if (status.toLowerCase().includes('progress') || status.toLowerCase().includes('live')) {
        searchQuery = `${team} vs ${opponent} live score ${sport}`;
    } else {
        searchQuery = `${team} vs ${opponent} game preview ${sport}`;
    }
    
    const encodedQuery = encodeURIComponent(searchQuery);
    window.open(`https://www.google.com/search?q=${encodedQuery}`, '_blank');
}

function searchForTeamStats(team, sport) {
    const searchQuery = `${team} ${sport} stats standings`;
    const encodedQuery = encodeURIComponent(searchQuery);
    window.open(`https://www.google.com/search?q=${encodedQuery}`, '_blank');
}

function shareGameResult(awayTeam, homeTeam, awayScore, homeScore) {
    const shareText = `${awayTeam} ${awayScore} - ${homeScore} ${homeTeam}`;
    
    if (navigator.share) {
        navigator.share({
            title: 'Game Result',
            text: shareText,
            url: window.location.href
        });
    } else {
        navigator.clipboard.writeText(shareText).then(() => {
            const btn = event.target;
            const originalText = btn.innerHTML;
            btn.innerHTML = '✅ Copied!';
            setTimeout(() => {
                btn.innerHTML = originalText;
            }, 2000);
        });
    }
}