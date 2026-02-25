const mongoose = require('mongoose');
const dotenv = require('dotenv');
const path = require('path');

// Load env vars
dotenv.config({ path: path.join(__dirname, '../.env') });

const movieSchema = new mongoose.Schema({
    title: String,
    year: Number,
    plot: String,
    genres: [String],
    cast: [String],
    runtime: Number,
    imdb: {
        rating: Number,
        votes: Number
    },
    type: String,
    released: Date
});

const Movie = mongoose.model('Movie', movieSchema);

const sampleMovies = [
    {
        title: "The Dark Knight",
        year: 2008,
        plot: "When the menace known as the Joker wreaks havoc and chaos on the people of Gotham, Batman must accept one of the greatest psychological and physical tests of his ability to fight injustice.",
        genres: ["Action", "Crime", "Drama"],
        cast: ["Christian Bale", "Heath Ledger", "Aaron Eckhart"],
        runtime: 152,
        imdb: { rating: 9.0, votes: 2300000 },
        type: "movie",
        released: new Date("2008-07-18")
    },
    {
        title: "Inception",
        year: 2010,
        plot: "A thief who steals corporate secrets through the use of dream-sharing technology is given the inverse task of planting an idea into the mind of a C.E.O.",
        genres: ["Action", "Adventure", "Sci-Fi"],
        cast: ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Elliot Page"],
        runtime: 148,
        imdb: { rating: 8.8, votes: 2100000 },
        type: "movie",
        released: new Date("2010-07-16")
    },
    {
        title: "The Matrix",
        year: 1999,
        plot: "A computer hacker learns from mysterious rebels about the true nature of his reality and his role in the war against its controllers.",
        genres: ["Action", "Sci-Fi"],
        cast: ["Keanu Reeves", "Laurence Fishburne", "Carrie-Anne Moss"],
        runtime: 136,
        imdb: { rating: 8.7, votes: 1700000 },
        type: "movie",
        released: new Date("1999-03-31")
    },
    {
        title: "Pulp Fiction",
        year: 1994,
        plot: "The lives of two mob hitmen, a boxer, a gangster and his wife, and a pair of diner bandits intertwine in four tales of violence and redemption.",
        genres: ["Crime", "Drama"],
        cast: ["John Travolta", "Uma Thurman", "Samuel L. Jackson"],
        runtime: 154,
        imdb: { rating: 8.9, votes: 1900000 },
        type: "movie",
        released: new Date("1994-10-14")
    },
    {
        title: "The Godfather",
        year: 1972,
        plot: "The aging patriarch of an organized crime dynasty transfers control of his clandestine empire to his reluctant son.",
        genres: ["Crime", "Drama"],
        cast: ["Marlon Brando", "Al Pacino", "James Caan"],
        runtime: 175,
        imdb: { rating: 9.2, votes: 1700000 },
        type: "movie",
        released: new Date("1972-03-24")
    }
];

const seedData = async () => {
    try {
        await mongoose.connect(process.env.MONGODB_URI);
        console.log('Connected to local MongoDB');

        // Clear existing movies
        await Movie.deleteMany({});
        console.log('Cleared existing movies');

        // Insert new movies
        await Movie.insertMany(sampleMovies);
        console.log('✅ Successfully seeded sample movie data into "movies" collection.');

        process.exit(0);
    } catch (error) {
        console.error('Error seeding data:', error);
        process.exit(1);
    }
};

seedData();
