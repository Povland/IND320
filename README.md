# IND320 project 2026
Philip A. K. Øvland

- GitHub: https://github.com/Povland/IND320
- Streamlit: https://ind320-2026.streamlit.app/


# Setup
'''
uv sync     # installs dependencies and the ind320 package
docker run --name my_cassandra -p 9042:9042 -d cassandra:latest
uv run streamlit run app/streamlit_app.py

MongoDB credentials go in `No_sync/atlas-credentials.env` (not in git), with the variables
`MONGODB_USERNAME`, `MONGODB_PASSWORD` and `MONGODB_URI`.

Windows: Spark needs Java 17 and winutils (Hadoop 3.3.x) in C:\hadoop\bin, with HADOOP_HOME=C:\hadoop.
'''