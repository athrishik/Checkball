// Global configuration object to store user preferences
let userConfig = {};

// Initialize the dashboard when page loads
document.addEventListener('DOMContentLoaded', function() {
    loadUserConfig();
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
    
    console.log(`Sport changed to: ${sport} for widget ${widgetIndex}`); // Debug log
    
    if (sport) {
        // Enable team dropdown and load teams
        teamSelect.disabled = false;
        teamSelect.innerHTML = '<option value="">Loading teams...</option>';
        
        // Fetch teams for the selected sport
        fetch(`/api/teams/${encodeURIComponent(sport)}`)
            .then(response => {
                console.log(`API response status: ${response.status}`); // Debug log
                return response.json();
            })
            .then(teams => {
                console.log(`Received ${teams.length} teams:`, teams); // Debug log
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
    
    console.log(`Game date: ${gameDate}, Now: ${now}, Diff days: ${diffDays}`); // Debug log
    
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
        document.getElementById(`team-name-${widgetIndex}`).textContent = data.team;
        document.getElementById(`team-score-${widgetIndex}`).style.display = 'none';
        document.getElementById(`opponent-name-${widgetIndex}`).textContent = data.opponent;
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
        document.getElementById(`team-name-${widgetIndex}`).textContent = data.team;
        document.getElementById(`team-score-${widgetIndex}`).textContent = data.team_score;
        document.getElementById(`team-score-${widgetIndex}`).style.display = 'block';
        document.getElementById(`opponent-name-${widgetIndex}`).textContent = data.opponent;
        document.getElementById(`opponent-score-${widgetIndex}`).textContent = data.opponent_score;
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
        venueElement.textContent = `📍 ${data.venue}`;
        venueElement.style.display = 'block';
    } else {
        venueElement.style.display = 'none';
    }
    
    // Display next game information (only if primary game is completed/in-progress)
    const nextGameElement = document.getElementById(`next-game-${widgetIndex}`);
    if (data.next_game && nextGameElement && !isUpcoming) {
        const nextGame = data.next_game;
        const formattedDate = formatGameDate(nextGame.game_date);
        nextGameElement.innerHTML = `
            <div class="next-game-label">Next:</div>
            <div class="next-game-details">vs ${nextGame.opponent} • ${formattedDate}</div>
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

// Optional: Auto-refresh scores every 5 minutes for live games only (commented out by default)
// Uncomment the lines below if you want automatic refresh for live games only
/*
function autoRefreshLiveGames() {
    for (let widgetId in userConfig) {
        const widgetIndex = parseInt(widgetId.split('_')[1]);
        const widget = userConfig[widgetId];
        
        if (widget.sport && widget.team) {
            // Only refresh if the widget is showing a live game
            const statusElement = document.getElementById(`status-${widgetIndex}`);
            if (statusElement && statusElement.textContent.includes('LIVE')) {
                fetchScores(widgetIndex, widget.sport, widget.team);
            }
        }
    }
}

// Set up auto-refresh interval for live games only (5 minutes)
let refreshInterval = setInterval(autoRefreshLiveGames, 5 * 60 * 1000);
*/

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

// Open game details in new tab
function openGameDetails(widgetIndex) {
    const teamName = document.getElementById(`team-name-${widgetIndex}`).textContent;
    const opponentName = document.getElementById(`opponent-name-${widgetIndex}`).textContent;
    
    if (teamName && opponentName && teamName !== 'No games found' && opponentName !== 'No games found') {
        // Create search query for the matchup
        const searchQuery = `${teamName} vs ${opponentName}`;
        const encodedQuery = encodeURIComponent(searchQuery);
        
        // Open Google search in new tab
        window.open(`https://www.google.com/search?q=${encodedQuery}`, '_blank');
    }
}

// Store game data for details functionality
let widgetGameData = {};

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

// Initialize enhanced features when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    addTeamSearch();
});

// Enhanced game details with modal functionality
function openGameDetails(widgetIndex) {
    const gameData = widgetGameData[widgetIndex];
    
    if (!gameData || gameData.opponent === 'No games found') {
        return;
    }

    // Open the modal instead of Google search
    openGameModal(widgetIndex);
}

// Game modal functionality
let gameModal = null;

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

async function loadGameDetails(widgetIndex) {
    const gameData = widgetGameData[widgetIndex];
    const sport = userConfig[`widget_${widgetIndex}`]?.sport;
    const modalContent = document.getElementById('gameModalContent');
    
    try {
        // Show loading state
        modalContent.innerHTML = `
            <div class="loading-spinner">
                <div class="spinner-icon">${getSportEmoji(sport)}</div>
                <p>Loading game details...</p>
            </div>
        `;

        // For now, we'll use the existing game data and enhance it
        // Later you could add a separate API endpoint for detailed stats
        
        await new Promise(resolve => setTimeout(resolve, 800)); // Simulate loading
        
        displayGameDetails(gameData, sport, widgetIndex);

    } catch (error) {
        modalContent.innerHTML = `
            <div class="error-message">
                <h3>Error Loading Game Details</h3>
                <p>Unable to fetch game information. Please try again later.</p>
            </div>
        `;
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

function displayGameDetails(gameData, sport, widgetIndex) {
    const modalContent = document.getElementById('gameModalContent');
    const isUpcoming = gameData.status_type === 'STATUS_SCHEDULED' && gameData.team_score === '-';
    const isLive = gameData.status_type === 'STATUS_IN_PROGRESS' || gameData.status_type === 'STATUS_HALFTIME';
    
    // Format date for display
    let gameDateTime = 'Unknown';
    if (gameData.game_date_iso) {
        try {
            const date = new Date(gameData.game_date_iso);
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
        <div class="game-header">
            <div class="game-matchup">${gameData.team} vs ${gameData.opponent}</div>
            <div class="game-info">
                ${gameData.status} | ${gameDateTime}<br>
                ${gameData.venue && gameData.venue !== 'TBD' ? `📍 ${gameData.venue}` : ''}
            </div>
        </div>

        <div class="stats-section">
            <div class="stats-title">${isUpcoming ? 'Upcoming Game' : isLive ? 'Live Score' : 'Final Score'}</div>
            ${!isUpcoming ? `
                <div class="score-display-modal">
                    <div class="team-score-modal">
                        <div class="team-name-modal">${gameData.team}</div>
                        <div class="score-modal">${gameData.team_score}</div>
                    </div>
                    <div class="vs-modal">vs</div>
                    <div class="team-score-modal">
                        <div class="team-name-modal">${gameData.opponent}</div>
                        <div class="score-modal">${gameData.opponent_score}</div>
                    </div>
                </div>
            ` : `
                <div class="upcoming-game-display">
                    <div class="upcoming-teams">${gameData.team} vs ${gameData.opponent}</div>
                    <div class="game-time">${formatGameDate(gameData.game_date_iso)}</div>
                </div>
            `}
        </div>

        ${gameData.next_game ? `
            <div class="stats-section">
                <div class="stats-title">Next Game</div>
                <div class="next-game-modal">
                    <div class="next-opponent">vs ${gameData.next_game.opponent}</div>
                    <div class="next-date">${formatGameDate(gameData.next_game.game_date)}</div>
                    ${gameData.next_game.venue ? `<div class="next-venue">📍 ${gameData.next_game.venue}</div>` : ''}
                </div>
            </div>
        ` : ''}

        <div class="modal-actions">
            <button onclick="searchForMoreDetails('${gameData.team}', '${gameData.opponent}', '${sport}', '${gameData.status}')" 
                    class="action-btn primary-btn">
                🔍 Search Game Details
            </button>
            <button onclick="searchForTeamStats('${gameData.team}', '${sport}')" 
                    class="action-btn secondary-btn">
                📊 Team Stats
            </button>
        </div>

        <div class="modal-footer">
            <div class="last-updated-modal">Last updated: ${gameData.last_updated}</div>
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

// Update your existing DOMContentLoaded event
document.addEventListener('DOMContentLoaded', function() {
    loadUserConfig();
    addTeamSearch();
    makeWidgetsClickable(); // Add this line
});