\# CheckBall ⚽🏀



A smart sports dashboard that prioritizes what matters most to fans - today's games, upcoming matches, and recent results.



!\[CheckBall Screenshot](https://via.placeholder.com/800x400/8B45FF/FFFFFF?text=CheckBall+Sports+Dashboard)



\## ✨ Features



\- \*\*Smart Game Prioritization\*\*: Shows live games first, then today's completed games, then upcoming games

\- \*\*Multi-Sport Coverage\*\*: NBA, WNBA, NFL, MLS, Premier League, La Liga, MLB, NHL

\- \*\*Dual Display Logic\*\*: Completed games show scores, upcoming games show times

\- \*\*Next Game Preview\*\*: Displays upcoming matchups below main scores

\- \*\*Individual Widget Control\*\*: Reconfigure any widget independently

\- \*\*Manual Refresh\*\*: Static display until "Check In" button clicked for better performance

\- \*\*Responsive Design\*\*: Works on desktop and mobile



\## 🛠️ Tech Stack



\- \*\*Backend\*\*: Python Flask + ESPN API

\- \*\*Frontend\*\*: Vanilla JavaScript + Modern CSS

\- \*\*Styling\*\*: Glassmorphism design with purple/blue theme

\- \*\*Data\*\*: Real-time sports scores and schedules



\## 🚀 Quick Start



\### Prerequisites

\- Python 3.7+

\- pip



\### Installation



1\. Clone the repository:

```bash

git clone https://github.com/yourusername/checkball.git

cd checkball

```



2\. Install dependencies:

```bash

pip install -r requirements.txt

```



3\. Run the application:

```bash

python checkball.py

```



4\. Open your browser to `http://localhost:5000`



\## 📱 Usage



1\. \*\*Select Sports\*\*: Choose from 8 different sports leagues

2\. \*\*Pick Teams\*\*: Select your favorite teams from comprehensive team lists

3\. \*\*Check Scores\*\*: Click "Check In" to get latest scores and schedules

4\. \*\*Game Details\*\*: Click the 🔍 button for more information about any game

5\. \*\*Reconfigure\*\*: Use the ⚙️ button to change teams without resetting the whole board



\## 🎯 Game Priority Logic



CheckBall intelligently displays games in this order:

1\. \*\*Live/In-Progress games\*\* (with pulsing animations)

2\. \*\*Today's completed games\*\* (with final scores)

3\. \*\*Recent completed games\*\* (yesterday or earlier)

4\. \*\*Upcoming games\*\* (shows times, not 0-0 scores)



\## 🎨 Design Features



\- \*\*Purple Theme\*\*: Modern gradient design with glassmorphism effects

\- \*\*Blue Accents\*\*: Check In/Reset buttons and developer credits

\- \*\*Live Game Indicators\*\*: Pulsing animations for games in progress

\- \*\*Responsive Grid\*\*: Perfect 2x2 layout that works on all screen sizes

\- \*\*Smooth Animations\*\*: Hover effects and loading states



\## 🔧 Configuration



The app uses ESPN's public API endpoints for real-time data:

\- No API keys required

\- Fetches 5-day window for optimal coverage

\- Eastern Time timezone conversion

\- Intelligent team name matching



\## 📊 Supported Sports



| Sport | Teams | Features |

|-------|-------|----------|

| NBA | 30 teams | Live scores, schedules |

| WNBA | 12 teams | Live scores, schedules |

| NFL | 32 teams | Live scores, schedules |

| MLS | 29 teams | Live scores, schedules |

| Premier League | 20 teams | Live scores, schedules |

| La Liga | 20 teams | Live scores, schedules |

| MLB | 30 teams | Live scores, schedules |

| NHL | 32 teams | Live scores, schedules |



\## 🚀 Deployment



\### Railway (Recommended)

1\. Push to GitHub

2\. Connect repo to \[Railway](https://railway.app)

3\. Auto-deploy on push



\### Heroku

```bash

heroku create checkball-app

git push heroku main

```



\### Local Development

```bash

export FLASK\_ENV=development

python checkball.py

```



\## 🤝 Contributing



1\. Fork the repository

2\. Create a feature branch (`git checkout -b feature/amazing-feature`)

3\. Commit your changes (`git commit -m 'Add amazing feature'`)

4\. Push to the branch (`git push origin feature/amazing-feature`)

5\. Open a Pull Request



\## 📝 License

## 📄 License & Attribution

CheckBall is open source under the MIT License. 

**If you use CheckBall:**
- ✅ Keep the "Developed by Hrishik Kunduru" credit in the footer
- ✅ Include the LICENSE file in your copy
- ✅ Star this repo if it helps you! ⭐

**You're free to:**
- Use for personal or commercial projects
- Modify and customize the code
- Distribute your own versions

**Just remember to give credit where it's due! 🙏**

This project is licensed under the MIT License - see the \[LICENSE](LICENSE) file for details.



\## 🙏 Acknowledgments



\- ESPN for providing sports data APIs

\- Sports fans everywhere for inspiration

\- Modern web design trends for the beautiful UI

\- M for being awesome and supportive always

\- Claude for hard carrying the CSS coding part

\## 📧 Contact



\*\*Hrishik Kunduru\*\* - \[@AtHrishik](https://linkedin.com/in/hrishikkunduru)



Project Link: \[https://github.com/athrishik/checkball](https://github.com/athrishik/checkball)



---



⭐

